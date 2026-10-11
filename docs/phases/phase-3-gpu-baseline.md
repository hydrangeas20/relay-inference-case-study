# Phase 3: Real GPU baseline and simulator calibration (Stage 3.0 readiness and design)

- **Status:** **PROPOSAL, for approval.** No Phase 3 code has been written.
  - No GPU has been provisioned and no paid experiment has run.
  - Nothing in Phase 2 was changed.
  - Wednesday wasn't accessed, and no Phase 2 traffic model is selected or used as validated.
- **Prepared:** 2026-10-10.
- **Independence from Phase 2:** Phase 2 (Candidate A, selection, the Wednesday lockbox) stays open and separate. Section 9 lists every dependency and how it's deferred.

Claim labels follow the [methodology](../methodology.md): ASSUMED, AZURE-DERIVED, CALCULATED, MEASURED, SIMULATED, PROJECTED.

---

## 1. Readiness audit: what exists, and what has actually been verified

| Component | Implemented | Verified how | Not yet verified |
|---|---|---|---|
| Gateway (`relay.gateway.app`): `/v1/complete`, `/v1/agent`, SSE pass-through, Prometheus metrics, 502 on upstream errors | Yes | Unit tests; real-socket end-to-end test (`tests/test_end_to_end.py`) against a fake OpenAI-compatible server | Against vLLM or the llm-d simulator; real tool-call streams; long prompts |
| Load generator (`relay.loadgen.runner`): open-loop replay, payloads prebuilt, client TTFT and E2E, rate and CPU self-check, three-layer TTFT reconciliation | Yes | Unit tests and the same end-to-end test (a VALID run whose TTFT layers reconcile) | Sustained high rate; multi-process; long runs; real network |
| Worker and bootstrap (SQS → embeddings → DynamoDB, bounded in-flight, retries) | Yes | Tests with mocked SQS and DynamoDB (`moto`) | Against Floci; against a real embedding endpoint |
| Trace builder (`relay-trace constant / day / window`): seeded, byte-reproducible, corpus-hashed | Yes | Identity and reproducibility tests | The `day` and `window` traces use Phase 2's **unvalidated** burstiness model (section 9) |
| Corpus (pinned, licence-hashed repos) | Yes | Tests | `make corpus` on a clean machine (needs GitHub access) |
| Docker Compose stack (Floci, llm-d-inference-sim v0.9.0, gateway, worker, Prometheus, Grafana) | Defined | CI: `docker compose config --quiet` only | **Never run.** `make up` / `make run` haven't run anywhere; this environment has no Docker daemon or GPU. Floci is unpinned (`:latest`) |
| Simulator latency parameters | Placeholders (TTFT 150 ± 30 ms, ITL 20 ± 5 ms, max-num-seqs 8) | — | Uncalibrated by design (methodology rule 3) |
| Results schema | `"phase1-provisional"` | — | The planned results schema was deferred, and is still open |
| vLLM / real GPU | Nothing yet | — | — |

**Checks run now:** the full suite (258 tests) passes. The 48 Phase 1 serving and measurement tests pass on their own (end-to-end, gateway, reconcile, self-check, traces, worker).

## 2. Timing definitions: audit

| Metric | Methodology definition | Current implementation | Gap |
|---|---|---|---|
| **Client TTFT** | Request sent → first output token received | `loop.time()` at send → first SSE line carrying content (text, delta content, or tool-call name/args). Monotonic clock | Correct for streamed requests. It includes the gateway, so it's the user-perceived value. **Not available for `stream: false`** |
| **Gateway upstream TTFT** | Nested inside the client's | From the start of `stream_upstream` (**after** the prompt is built) to the first content chunk | Excludes the gateway's request parsing and prompt building. Defensible, but should be documented, and a separate gateway-receipt timer added |
| **Server TTFT** | vLLM's `time_to_first_token_seconds` | Scraped before and after; diffed; dominance-checked against the inner layers | Histogram resolution only. Bucket bounds must be checked against the exact vLLM version |
| **ITL** | Time between consecutive output tokens | **Not recorded.** Only `n_chunks` and `output_chars` | **P0 gap:** per-chunk arrival times aren't kept, so ITL and TPOT can't be computed |
| **Output tokens** | Throughput is output tokens per second | Chunks and characters only (ADR-0003 Q5) | **P0 gap:** request `stream_options: {"include_usage": true}` and record the server's `prompt_tokens` and `completion_tokens`. A chunk isn't guaranteed to be one token |
| **E2E latency** | Request sent → final token received | Send → stream closed (after `[DONE]` or the connection end) | Doesn't distinguish a completed stream from a truncated one. No check that `[DONE]` or a `finish_reason` arrived |
| **Throughput** | Output tok/s across all requests | Not computed | Needs token counts, and a steady-state window (warm-up and cool-down excluded) |
| **Goodput** | Requests per second meeting their SLO | Not computed | Needs the SLO definitions applied per request |
| **Error rate** | — | `status`: `ok`, `http_<code>`, `error:<ExceptionType>`, `empty_response`, per workload | No taxonomy for timeouts vs. connection errors vs. truncated streams. No rule for when errors invalidate a run (as opposed to being a result) |
| **Send lag, generator CPU** | Rule 4 | Rate shortfall > 2% or CPU p95 ≥ 90% of one core ⇒ invalid | Single process only; rule 4's "scale out" isn't implemented |
| **Reconciliation** | — | Stochastic-dominance check across server ≤ gateway ≤ client, plus the request count | Disagreement is reported but doesn't invalidate the run (ADR-0003 Q2, open) |

## 3. Local end-to-end smoke test (no GPU): design

| Level | What | Runs where | Status |
|---|---|---|---|
| **L0** | pytest real-socket end-to-end test (load generator → gateway → fake server, in-process threads) | CI | **Exists and passes** |
| **L1** | **Harness known-answer smoke**: a runnable fake server (`relay.fakeserver`), the gateway and the load generator as separate processes on localhost | Any laptop, and CI | Proposed |
| **L2** | `make up && make run` with the Compose stack (llm-d simulator, Floci, Prometheus) | Owner's machine with Docker | Proposed (first run ever) |
| **L3** | The same stack with `INFERENCE_BACKEND=gpu`, pointed at vLLM on the rented GPU (one config change) | GPU host | Stage 3.3 |

**L1 design (no new dependencies):**
1. **Promote the test fake to a CLI module.** Add configurable deterministic TTFT and ITL, a chunk count, a final usage chunk, `finish_reason`, and error and truncation injection.
2. **Use a synthetic corpus**, as the end-to-end test does, so the smoke run needs no network.
3. **Known-answer assertions:**
   - **Deterministic case** (TTFT 50 ms, ITL 10 ms, 20 tokens):
     - client TTFT ≥ 50 ms, and client TTFT − server TTFT ≤ a harness-overhead bound, reported as the **measurement floor**;
     - ITL p50 within 10 ms ± 2 ms;
     - token counts exactly 20;
     - the self-check is VALID and reconciliation is consistent.
   - **Injected 5xx:** classified correctly; the run still completes.
   - **Truncated stream** (no `[DONE]`): classified as truncated, not `ok`.
   - **Overload** (fake server with a concurrency limit): latency rises; the load generator stays open-loop (send lag is flat).
4. **Output:** a results-schema-v1 file with full provenance (section 7). Running the same command twice gives identical deterministic fields.

L1 validates **the instrument**, not the server. The same known-answer run is repeated on the GPU host before any GPU measurement (Stage 3.3), to measure the harness floor on that machine.

## 4. Proposed real-GPU baseline matrix

**Baseline server configuration** (pinned; changed only in M4):
- vLLM at one pinned release (image digest recorded);
- BF16, default scheduler, chunked prefill at the default, prefix caching **off** (RLY-4 owns it);
- `max-num-seqs` at the default;
- temperature 0 and `seed` set per request.
- Fixed output lengths use `ignore_eos` or `min_tokens` (both vLLM sampling extensions). For prompt lengths in tokens, the model's tokenizer is used.

All load runs are **open-loop** (rule 4). M1 is serial and M4b is a closed-loop probe; both are labelled characterisation, not load tests.

| ID | Purpose | Factors | Runs × duration | Role |
|---|---|---|---|---|
| **M0** | Harness floor on the GPU host; liveness | L1 known-answer run against the fake, then 50 requests to vLLM | 1 × 10 min | Gate |
| **M1** | Prefill and decode cost per request | ISL {128, 512, 1K, 2K, 4K, 8K} × OSL {16, 128, 512}; concurrency 1; 30 requests per cell | 18 cells × 3 reps, about 1 h | **Calibration** |
| **M2** | Latency–throughput curve, fixed shapes | Shape S-C (ISL 2K / OSL 64, completion-like) and S-A (ISL 4K / OSL 256, agent-like); Poisson rates at {0.25, 0.5, 0.7, 0.8, 0.9, 1.0, 1.1} × λ_sat. λ_sat comes from one probe run per shape | 2 × 7 × 3 reps × 5 min (1 min warm-up) = 3.5 h | 0.25 / 0.5 / 0.8 → **calibration**; 0.7 / 0.9 / 1.0 / 1.1 → **validation** |
| **M3** | Realistic sizes | (context, output) pairs from `azure_code_sizes.csv` (**training days only**; AZURE-DERIVED: context p50 1,899, p95 7,673; output p50 8, p95 82, max 5,000), capped at the model context. Poisson rates {0.5, 0.8, 1.0} × λ_sat | 3 × 3 reps × 5 min = 0.75 h | **Validation** (distribution shift) |
| **M4** | Batching and scheduler sensitivity (simulator inputs) | (a) open-loop at 0.8 × λ_sat: `max-num-seqs` {16, 64, 256} × `max-num-batched-tokens` {2048, 8192}; (b) closed-loop concurrency probes {1, 4, 16, 64}, characterisation only | (a) 6 × 2 reps × 5 min = 1 h; (b) 0.5 h | Calibration (only if the simulator takes these knobs); otherwise reported |
| **M5** | Streaming overhead | `stream` true vs false at 3 rates, shape S-C | 2 × 3 × 3 × 5 min = 1.5 h | Reported |
| **M6** | Cold vs warm | 5 × {container start → weights loaded → `/health` ready → first token} with weights on local disk; 1 × with a weight download (once); first-N-requests vs steady-state latency after ready | 0.5–1 h | Reported; RLY-2 input |
| **M7** | Mixed workload | 80/15 completion/agent (Phase 1 placeholder mix; agent with tool calls), Poisson at 0.8 × λ_sat | 3 reps × 10 min = 0.5 h | **Validation** |
| **M8** | Independent repeat | M2 validation rates on a **separate session or day** (and instance, if possible) | 1.5 h | **Validation**, and the noise floor |
| **Q0** | Quality baseline (methodology rule 2) | BF16 baseline eval for completions and tool-call validity; benchmark choice pending | 1–2 h | Quality reference for RLY-3 and RLY-6 |

Embeddings (the worker path) are a separate small session: the same GPU, a second vLLM process for the embedding model, and throughput-only measurement. It's not part of the latency baseline.

## 5. Hardware and model: requirements and VRAM

**Model (decision P3-1):** a public stand-in for Relay's "fine-tuned ~7B code model". Proposed: **Qwen2.5-Coder-7B-Instruct** (Apache-2.0).
- **Why:** it handles chat and tool calls (vLLM's tool parser), has a native 32K context, and its FIM tokens are available in the base variant.
- **FIM (ADR-0003 Q4):** use the instruct model for both endpoints (FIM unused), or a base/instruct pair. **Owner decision.**
- **Embedding model:** a small Apache or MIT model (for example BAAI/bge-small-en-v1.5).
- **Pinning:** the exact Hugging Face revision hash and the weight-file hashes are recorded.

**VRAM** (CALCULATED from the model architecture: 7.61B parameters; 28 layers; 4 KV heads × 128 dims; BF16):
- weights ≈ **15.2 GB**;
- KV cache = 2 × 28 × 4 × 128 × 2 B = **57,344 B per token**;
- runtime overhead (activations, CUDA graphs) **about 2 GB** (ASSUMED);
- `gpu-memory-utilization` = 0.90.

| GPU | Usable | KV budget | KV tokens | Concurrent sequences at 2K context | FP8 W8A8 (for RLY-3) |
|---|---|---|---|---|---|
| L4 24 GB | 21.6 GB | ≈ 4.4 GB | ≈ 77K | ≈ 37 | Yes (Ada) |
| A100 40 GB | 36 GB | ≈ 18.8 GB | ≈ 330K | ≈ 160 | No (INT8 or weight-only) |
| L40S 48 GB | 43.2 GB | ≈ 26 GB | ≈ 450K | ≈ 220 | Yes (Ada) |
| A100 / H100 80 GB | 72 GB | ≈ 55 GB | ≈ 950K | ≈ 460 | H100 yes; A100 no |

**Proposed (decision P3-2):** **L40S 48 GB** as the baseline GPU.
- Enough KV headroom that the baseline isn't KV-bound at 8K contexts.
- FP8-capable, so RLY-3's quantization comparison stays on the same hardware.
- Mid-priced.
- **L4** is the RLY-3 right-sizing target, measured later on the same matrix subset. **H100** is the alternative if L40S isn't available.

**Cost control** (nothing provisioned):
- one GPU, on-demand, in a single region;
- a hard spending cap per session and overall;
- auto-shutdown after 30 minutes idle;
- all images and weights prefetched before the meter matters (pulled once to a persistent volume);
- the matrix is scripted and resumable, so no interactive debugging happens on the paid instance;
- L1 and L2 pass locally first;
- a run log records instance-hours and cost.

## 6. Simulator calibration and evaluation

**Which simulator (decision P3-3).**
- **llm-d-inference-sim** (in the Compose file) takes a fixed TTFT / ITL distribution plus a load factor. Whether its pinned version models prompt-length-dependent prefill and batch-dependent decode **must be verified against its documentation for that version** before choosing it.
  - If it can't express M1's dependence on prompt length, it can only be calibrated for a fixed shape.
  - Its scope claims would then be limited to that shape.
- **Vidur** (profiling-based) is the alternative for capacity projections (`source: projection`).
- Proposal: verify llm-d's capabilities first, then choose. Both must be pinned.

**Split (no tuning on validation data):**
- **Calibration set:** M1; M2 at {0.25, 0.5, 0.8} × λ_sat; M4 (if used).
- **Validation set:** M2 at {0.7, 0.9, 1.0, 1.1} × λ_sat (interpolation and saturation); M3 (realistic sizes); M7 (mixed workload); M8 (an independent session).
- Validation runs are executed **after** the calibrated parameters are frozen and committed. Each is run once, with no refitting afterwards.
- Different trace seeds are used for calibration and validation traffic.

**Fit:** the simulator's parameters minimise the summed squared log-ratio between simulated and GPU values on the calibration set. The quantities are TTFT p50/p95/p99, ITL p50/p95, E2E p95 and output throughput. Same trace, same arrival times, same lengths (rule 5).

**Evaluation (preregistered before validation runs, decision P3-4):**
- **Reported:** ratios sim/GPU per validation condition and metric.
- **Proposed acceptance** (rule 3: "calibration error is reported, and conclusions smaller than it aren't drawn"):
  - |log ratio| ≤ log 1.2 for TTFT p50/p95, ITL p50 and throughput, at rates ≤ 0.9 × λ_sat;
  - the saturation rate within ±15%.
  - p99 and ≥ 1.0 × λ_sat are reported, not gated.
- **Calibrate the criterion before trusting it** (the Phase 2 lesson). The same rule is first applied **GPU against GPU**, comparing M8 with the original M2 runs. If the GPU can't pass against itself, the tolerance is too tight. It must be widened **before** the simulator is evaluated, by a dated amendment.

**Outcome:** the calibration error per metric and condition is published. Simulator-based claims (`source: sim` / `projection`) carry it, and simulator differences smaller than it aren't reported as findings.

## 7. Provenance, seeds, invalid runs, uncertainty, stopping

**Results schema v1** (decision P3-5; it replaces `"phase1-provisional"`). Fields:

| Group | Fields |
|---|---|
| Identity | `run_id`, `source` (`gpu` / `sim` / `projection` / `floci`), `stage` and `matrix_id` (for example M2/S-C/0.8/rep2), `role` (`calibration` / `validation` / `reported`) |
| Code | `git_commit` and dirty flag; load generator and gateway versions |
| Traffic | Trace path and SHA-256, `trace_id`, `spec_id`, seed, `generator_sha256`, corpus SHA-256 |
| Server | vLLM version and image digest; full launch arguments; model ID, Hugging Face revision and weight hashes; tokenizer revision; dtype |
| Hardware | `nvidia-smi` (GPU, driver, CUDA, clocks, power limit, ECC); CPU and RAM; provider, region, instance type |
| Run | Timestamps; warm-up and cool-down policy; self-check; reconciliation; per-request raw file hash |
| Telemetry | GPU utilisation, memory, power, clocks and throttle reasons; vLLM running/waiting queue, KV usage and preemptions |
| Cost | Instance-hours and cost for the session |

**Seeds:**
- One trace seed per (matrix cell, role). Repetitions **replay the identical trace** (rule 5), so variation between reps is the server's and the platform's.
- A separate seed set is used for validation traffic.
- Request-level `seed` is passed to vLLM. Temperature is 0.
- Simulator seeds are recorded.

**A run is invalid (discarded, logged, not reported as data) if:**
- the self-check fails;
- reconciliation is inconsistent (proposed: makes calibration and validation runs invalid; closes ADR-0003 Q2);
- server and client request or token counts differ;
- fixed-OSL requests don't produce the requested length;
- the stream is truncated outside an overload condition;
- another process holds the GPU;
- the server restarts mid-run;
- GPU throttle reasons other than idle are active for more than 5% of samples;
- the error rate is > 1% at load ≤ 0.9 × λ_sat. At ≥ 1.0 × λ_sat, errors are **results**, not invalidity.

**Uncertainty:**
- Client latencies use exact per-request samples. Server histograms are used for reconciliation only (bucket resolution reported).
- Per run: percentiles with **block-bootstrap** 95% intervals (blocks of 30 s, because latency is autocorrelated under load).
- Across runs: the median, with the min–max range, of ≥ 3 reps (rule 7).
- Minimum samples: ≥ 1,000 steady-state requests for any p99, otherwise p99 isn't reported; ≥ 200 for p95.
- A difference smaller than the across-rep spread isn't called a change.

**Stopping:**
- **Per-session:** stop at the cost cap.
- **Same-cause invalidity:** stop after 2 consecutive invalid runs with the same cause, and investigate locally.
- **Rate sweeps:** stop after two points beyond saturation (p99 TTFT > 10× the low-load value, or errors > 5%).
- **Unstable hardware:** stop and release the instance.

## 8. Instrumentation gaps and prioritised fixes

| Priority | Gap | Fix |
|---|---|---|
| **P0** | No ITL / TPOT | Record per-chunk arrival offsets (compressed) in the raw records; compute ITL per request |
| **P0** | No true token counts | `stream_options.include_usage`; record `prompt_tokens`, `completion_tokens` and `finish_reason`; tokenizer-based prompt sizing |
| **P0** | Can't control prompt and output lengths | A new trace type `fixed` (ISL and OSL in tokens; `ignore_eos` / `min_tokens`), plus an `azure-sizes` sampler (training days only) |
| **P0** | Truncated streams count as `ok` | Require `[DONE]` or a `finish_reason`; add an error taxonomy (timeout / connect / http / truncated / empty) |
| **P0** | No results schema or provenance | Schema v1 (section 7), with automatic capture of git, server, model and GPU details |
| **P0** | No steady-state window | Warm-up and cool-down trimming in the summary; throughput and goodput over the window |
| **P1** | Load generator always goes through the gateway | A `--target server` mode that calls vLLM directly, so gateway overhead can be isolated |
| **P1** | Only before/after scrapes | Periodic scrape of vLLM metrics during the run (queue, KV, preemptions); confirm metric names against the pinned vLLM version |
| **P1** | No GPU telemetry | `nvidia-smi` sampling, or DCGM exporter, into the run record |
| **P1** | Single load-generator process | Multi-process load generation, with a merged self-check |
| **P1** | No cold-start timing | An M6 harness: container start, model loaded, ready, first-token timestamps |
| **P2** | Gateway TTFT starts after prompt build | Add a gateway-receipt timer, and document the nesting |
| **P2** | Floci `:latest`; no GPU Compose profile | Pin digests; add a `gpu` profile (vLLM service with a device reservation) |
| **P2** | ADR-0003 Q2/Q3 open | Decide (proposal: reconciliation inconsistency invalidates calibration and validation runs) |

## 9. Dependencies on unfinished Phase 2 work, explicitly deferred

| Phase 2 item | Phase 3 use | Handling |
|---|---|---|
| **Burstiness model** (Candidate D provisional; A pending; Wednesday not run) | Realistic arrival processes | **Deferred.** Phase 3 uses Poisson and fixed-rate arrivals only. The `day` and `window` trace types (which use the unvalidated model) aren't used for calibration or validation. Simulator evaluation under bursty traffic waits for Phase 2 selection |
| Selection of a final traffic model | Capacity planning (Phase 5) | Deferred; no selection is made or implied |
| `azure_code_sizes.csv` | M3 request sizes | **Usable:** derived from the training days only (Fri–Tue), committed and authorised. No Thursday- or Wednesday-derived data is used |
| Results schema (deferred from Phase 2) | All Phase 3 results | Defined in Phase 3 (P3-5), independent of the traffic model |
| Wednesday lockbox | — | Never accessed by Phase 3 |

**Branching.** The Phase 3 work sits on its own branch. It's based on `phase-2-traffic-model` only because that branch carries the Phase 1 code and the committed size reference. No Phase 2 file is modified.

## 10. Compute budget (estimate)

GPU hours per stage (CALCULATED from the matrix):

| Stage | Hours |
|---|---|
| Setup: image pull, weights, M0, L3 checks | 3 |
| M1 | 1 |
| M2 | 3.5 |
| M3 | 0.75 |
| M4 | 1.5 |
| M5 | 1.5 |
| M6 | 1 |
| M7 | 0.5 |
| M8 | 1.5 |
| Q0 | 2 |
| **Subtotal** | **≈ 16 h** |
| Contingency (×1.3) | **≈ 21 h** |
| Minimal path (M0, M1, M2, M3, M7, M8, Q0) | ≈ 12–14 h |

**Cost (ASSUMED price ranges; not checked against live quotes, which must be confirmed at provisioning):**

| GPU | Price range | Plan cost | Minimal path |
|---|---|---|---|
| L40S | ≈ $0.80–1.50 / h | ≈ $17–32 | ≈ $10–21 |
| H100 80 GB | ≈ $2–3.50 / h | ≈ $42–74 | — |

Persistent storage for weights (≈ 20 GB) is extra but small. **Proposed hard cap:** $60 for the whole of Phase 3's baseline (owner to set).

## 11. Stage plan (each stage ends at a review)

| Stage | Content | GPU | Exit criterion |
|---|---|---|---|
| **3.0** | This readiness audit and design | No | **Owner approval of the decisions in section 12** |
| **3.1** | P0 instrumentation (ITL, usage tokens, truncation, error taxonomy, schema v1, provenance, steady-state window); the `fixed` and `azure-sizes` trace types; tests | No | Tests and CI pass |
| **3.2** | L1 harness smoke (runnable fake, known-answer assertions) in CI. L2: `make up && make run` on the owner's machine. P1 items (direct-to-server mode, periodic scrapes, GPU telemetry stub, multi-process load generator, cold-start harness) | No | L1 green in CI; L2 run log from a real machine |
| **3.3** | Preregister the calibration and validation split, the acceptance rule and invalid-run criteria (a dated document, committed before any GPU run). Provisioning script with cost guards. M0 | **Yes**, first paid hour | M0 VALID; harness floor measured |
| **3.4** | Calibration runs (M1, M2-cal, M4); Q0 quality baseline | Yes | All runs VALID or logged as invalid |
| **3.5** | Fit the simulator; freeze and commit its parameters | No | Parameters committed |
| **3.6** | Validation runs (M2-val, M3, M7, M8), each once; GPU-vs-GPU criterion check first | Yes | Calibration error published |
| **3.7** | Phase 3 report; simulator scope statement; inputs to RLY-1 through RLY-4 | No | Review |

## 12. Decisions requested before Stage 3.1

| ID | Decision | Proposal |
|---|---|---|
| P3-1 | Model, FIM, embedding model | Qwen2.5-Coder-7B-Instruct for both endpoints (FIM unused); bge-small-en-v1.5 |
| P3-2 | GPU | L40S 48 GB baseline; L4 later for RLY-3; H100 as fallback |
| P3-3 | Simulator | Verify llm-d-inference-sim's capabilities at its pinned version first; Vidur for projections |
| P3-4 | Calibration acceptance rule | ±20% (log 1.2) on TTFT p50/p95, ITL p50 and throughput at ≤ 0.9 × λ_sat; saturation ±15%; GPU-vs-GPU check first |
| P3-5 | Results schema v1 | Section 7 fields |
| P3-6 | ADR-0003 Q2/Q3 (reconciliation) | Inconsistency invalidates calibration and validation runs; the client–server gap is reported, not judged |
| P3-7 | Closed-loop characterisation (M1, M4b) as labelled exceptions to rule 4 | Allowed, labelled "characterisation, not a load test" |
| P3-8 | Budget cap and idle shutdown | $60 total; 30 min idle |
| P3-9 | Matrix scope | Full plan, or the minimal path (section 10) |
