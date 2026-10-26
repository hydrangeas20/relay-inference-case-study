# RLY-4 walkthrough: "We turned on prefix caching. Nothing changed."

**Status:** measured on CPU; the confirmation run and GPU validation are outstanding.

**Source tag:** `cpu`. llama.cpp on one CPU thread, running a model with seeded synthetic weights on a controlled editing-session workload.

**Implementation PR:** [#3](https://github.com/hydrangeas20/relay-inference-case-study/pull/3), merged in [`b1847ea`](https://github.com/hydrangeas20/relay-inference-case-study/commit/b1847ea4ce31130420ab150ffe9b63df30dd14e0).

**Supporting documents:**
- **Ticket brief:** [README.md](README.md)
- **Predictions:** [PREDICTIONS.md](PREDICTIONS.md)
- **Method:** [ADR-0007](../../docs/decisions/0007-cpu-engine-and-rly4-method.md)
- **Independent review:** [review/](review/)

**Traceability chain:** [problem](#1-the-problem) → [hypothesis](#2-how-i-investigated) → [code change](#4-the-engineering-fix) → [tests](#6-how-i-tested-it) → [evidence](#7-results) → [conclusion](#3-root-cause) → [limitations](#8-trade-offs-and-limitations)

---

## 1. The problem

Relay's inline completions send long prompts: a system prompt plus the file being edited, 1,470–2,400 tokens in this workload. Before the model can write its first token, the engine has to process every one of those tokens (*prefill*). That wait is most of the time to first token (TTFT), which is the number users feel while typing.

A **prefix cache** keeps the processed state of earlier prompts. When a new prompt starts with the same tokens, the engine skips them. In an editing session, each request repeats almost all of the previous one, so caching should help a lot.

Relay turned prefix caching on, and TTFT didn't improve. That's the complaint this ticket investigates ([ticket brief](README.md)).

**What was planted, and what was measured.** Relay is a fictional customer. This bug was deliberately written into Relay's prompt template when the case study was designed; the ticket brief labels its root cause "planted". Nothing was discovered. What this ticket did was build the instrumentation, workload and controls to test the hypothesis on a real engine, measure the effect of the bug and of the fix, and report the predictions that failed.

## 2. How I investigated

**Hypothesis (H1).** Relay's template starts every prompt with a per-request header: `[relay request_id=… ts=…]`. A prefix cache can only reuse tokens up to the *first* difference, so a unique header at the front would make every prompt unique almost immediately, whatever follows.

**Alternatives the design had to rule out:**
- **The cache is off or broken.** Tested with a cache-off control: the same template and traffic, with the server's prompt cache disabled.
- **Prompts don't actually repeat.** Tested with a negative control: identical arrival times and cursor positions, but every request uses a different file.
- **The gain is just queueing.** Separated by measuring server-side prefill time, which excludes time spent waiting in the queue, alongside client TTFT.

**Choosing a backend that really caches.** The project's simulator can't answer this question: its latency doesn't depend on prompt length, and it doesn't model caching. No GPU or downloadable weights were available. So the experiment used a real engine, llama.cpp's `llama-server` on CPU. The model has a Qwen2 architecture with seeded random weights and the real Qwen2 tokenizer. The reasoning and its limits are recorded in [ADR-0007](../../docs/decisions/0007-cpu-engine-and-rly4-method.md).

**Evidence collected on every request:**
- client TTFT;
- the server's own report of tokens reused from cache (`cache_n`) and tokens processed (`prompt_n`);
- the server's Prometheus counters before and after each run;
- a run manifest (git commit, environment, gateway setting, engine build, model hash).

**Predictions came first.** Predictions and falsification thresholds were committed in [`752d1c1`](https://github.com/hydrangeas20/relay-inference-case-study/commit/752d1c1acf6d3fdec1cf780107d6b3e10fbaff56), before any full run's results were read. A 6-request pipeline pilot had been seen and is disclosed in [PREDICTIONS.md](PREDICTIONS.md).

## 3. Root cause

The header defeated the cache. Four pieces of evidence, all recomputed from raw records in [review/recompute-output.txt](review/recompute-output.txt):

1. **Almost no reuse.** With the original template, the engine reused **0.5%** of prompt tokens. Per request, that's 0, 7 or 10 tokens: the shared opening of the header text.
2. **Only the header differs.** Original prompts are exactly 60 characters (43 tokens) longer than fixed ones on every request. Nothing else changed.
3. **Large reuse once it's gone.** With the header removed and the cache on, reuse rose to **82.9%**. With the cache off, it was 0%, and the fix's gain disappeared (paired TTFT ratio cache-on vs cache-off: 0.24). The cache is what delivers the gain.
4. **Needs repeated context.** When context doesn't repeat (the negative control), the fix gains only about 10% (ratio 0.90). Only the system prompt can be reused.

## 4. The engineering fix

**Request metadata leaves the prompt.** The gateway now sends the request ID as an `X-Request-Id` HTTP header instead of prompt text.

**Why not move the header to the end?** An inline-completion prompt ends at the user's cursor. Text appended there would sit between the code and the completion the model is asked to write.

**Nothing is lost:**
- nothing in Relay read the ID or timestamp from the prompt;
- the ID still reaches the inference server, and a test checks it;
- the timestamp had no consumer.

**Relay's original template is kept** byte-for-byte as the default (`PROMPT_TEMPLATE=original`), so the before/after comparison stays exact.

## 5. How to inspect the code

| What | Where | Commit |
| --- | --- | --- |
| Template switch: `TemplateVariant`, `_header`, `completion_prompt(..., variant=)` | [`src/relay/gateway/templates.py`](../../src/relay/gateway/templates.py) | [`b48f20e`](https://github.com/hydrangeas20/relay-inference-case-study/commit/b48f20ea6d9c19eacffbc6797ef80edd72958b8d) |
| `REQUEST_ID_HEADER` sent upstream in `stream_upstream`; `GET /info` reports the active template | [`src/relay/gateway/app.py`](../../src/relay/gateway/app.py) | [`b48f20e`](https://github.com/hydrangeas20/relay-inference-case-study/commit/b48f20ea6d9c19eacffbc6797ef80edd72958b8d) |
| Settings: `prompt_template`, the `cpu` source tag, `loadgen_send_lag_p99_limit_ms` | [`src/relay/config.py`](../../src/relay/config.py) | [`b48f20e`](https://github.com/hydrangeas20/relay-inference-case-study/commit/b48f20ea6d9c19eacffbc6797ef80edd72958b8d), [`2918b7c`](https://github.com/hydrangeas20/relay-inference-case-study/commit/2918b7c081a3dd159887ed714526a03dcf596102) |
| Editing-session traces: `SessionParams`, `generate_sessions` | [`src/relay/traces/sessions.py`](../../src/relay/traces/sessions.py) | [`b48f20e`](https://github.com/hydrangeas20/relay-inference-case-study/commit/b48f20ea6d9c19eacffbc6797ef80edd72958b8d) |
| Per-request engine timings: `chunk_timings`; `server_timing_summary` | [`src/relay/sse.py`](../../src/relay/sse.py), [`src/relay/loadgen/runner.py`](../../src/relay/loadgen/runner.py) | [`b48f20e`](https://github.com/hydrangeas20/relay-inference-case-study/commit/b48f20ea6d9c19eacffbc6797ef80edd72958b8d) |
| Run manifest: `collect`, `inference_server` | [`src/relay/manifest.py`](../../src/relay/manifest.py) | [`b48f20e`](https://github.com/hydrangeas20/relay-inference-case-study/commit/b48f20ea6d9c19eacffbc6797ef80edd72958b8d) |
| Validity gate: `check(..., send_lag_p99_limit_s=)`, `RLY4_SEND_LAG_P99_LIMIT_S` | [`src/relay/loadgen/selfcheck.py`](../../src/relay/loadgen/selfcheck.py) | [`b48f20e`](https://github.com/hydrangeas20/relay-inference-case-study/commit/b48f20ea6d9c19eacffbc6797ef80edd72958b8d), [`2918b7c`](https://github.com/hydrangeas20/relay-inference-case-study/commit/2918b7c081a3dd159887ed714526a03dcf596102) |
| Synthetic-weight model builder | [`make_model.py`](make_model.py) | [`b48f20e`](https://github.com/hydrangeas20/relay-inference-case-study/commit/b48f20ea6d9c19eacffbc6797ef80edd72958b8d) |
| Experiment runner (fresh server per run, CPU pinning, 10 ms limit) | [`run_experiment.sh`](run_experiment.sh) | [`b48f20e`](https://github.com/hydrangeas20/relay-inference-case-study/commit/b48f20ea6d9c19eacffbc6797ef80edd72958b8d), [`c50dd32`](https://github.com/hydrangeas20/relay-inference-case-study/commit/c50dd3267775e7c8f88475615a2751b43334e78f) |
| Replayed traces | [`traces/rly4-shared.jsonl`](../../traces/rly4-shared.jsonl), [`traces/rly4-independent.jsonl`](../../traces/rly4-independent.jsonl) | [`cb7d80d`](https://github.com/hydrangeas20/relay-inference-case-study/commit/cb7d80d3b59fc9926341298211a385735e22a5ca) |
| Report generator; independent recomputation | [`analyze.py`](analyze.py), [`review/recompute.py`](review/recompute.py) | [`d46f478`](https://github.com/hydrangeas20/relay-inference-case-study/commit/d46f4787580141823817a85175fdc12ebdaa53ea), [`796e8c9`](https://github.com/hydrangeas20/relay-inference-case-study/commit/796e8c9f3437c695f4d0615f0762cd8a22e6eb87) |

The full diff is in PR [#3](https://github.com/hydrangeas20/relay-inference-case-study/pull/3/files).

## 6. How I tested it

**Regression tests** in [`tests/test_rly4.py`](../../tests/test_rly4.py). None needs a model:

| Test | What it pins |
| --- | --- |
| `test_original_template_prompts_diverge_within_the_header` | The bug: two original-template prompts share only the header's opening |
| `test_original_template_is_unchanged` | The baseline stays byte-for-byte Relay's template |
| `test_metadata_template_session_prompts_extend_each_other` | The fix: each later prompt in a session starts with the entire earlier prompt |
| `test_gateway_info_and_request_id_header` | The request ID still reaches the server as `X-Request-Id` in both variants |
| `test_shared_and_independent_share_one_schedule` | The negative control has the same arrival times and cursors as the main trace |
| `test_session_trace_is_deterministic` | The same seed gives an identical trace |

**Validity tests** in [`tests/test_stats_and_selfcheck.py`](../../tests/test_stats_and_selfcheck.py):
- `test_selfcheck_burst_then_catch_up_is_invalid`
- `test_selfcheck_steady_drift_is_caught_by_send_lag`
- `test_send_lag_only_gates_when_an_experiment_sets_a_limit`

**Evidence-consistency tests** in [`tests/test_rly4_evidence.py`](../../tests/test_rly4_evidence.py). They check that the raw records, both cache telemetry sources, the generated report and the independent recomputation all agree, and they pin the headline figures.

**Experiment design** (full table in the [ticket write-up](README.md#experiment-design)):

| | |
| --- | --- |
| Workload | 8 editing sessions × 6 completions over real source files. Poisson arrivals at 0.25 requests/s. Fixed 8 output tokens |
| One change at a time | Template (`original` / `metadata`) × server prompt cache (on / off) |
| Negative control | Same schedule, no repeated file context |
| Repetitions | 3 per configuration, fresh server each run, server and client pinned to separate cores |
| Validity | A run is excluded if send-lag p99 exceeds 10 ms. Excluded runs are kept and listed |

**CI:** lint, strict type checks and the test suite on every PR, plus a Docker stack smoke test ([workflows](../../.github/workflows/)).

## 7. Results

All figures come from [`results/rly-4/report.md`](../../results/rly-4/report.md) and the raw records in [`results/rly-4/`](../../results/rly-4/). The independent [review/recompute-output.txt](review/recompute-output.txt) reproduces them.

| Same 48 requests | Original template | Fixed template |
| --- | --- | --- |
| Prompt tokens served from cache | 0.5% | 82.9% |
| Median TTFT (median of per-run p50s) | 2,524 ms | 654 ms (3.9x lower) |
| p95 TTFT (median of per-run p95s) | 5,799 ms | 2,013 ms (2.9x lower) |
| Paired per-request TTFT ratio | — | 0.22 (0.210 / 0.223 / 0.220 by repetition) |
| Server-side prefill time ratio (queue-free) | — | 0.24 |

**Predictions** ([PREDICTIONS.md](PREDICTIONS.md)). Four held cleanly: P1, P2, P3 and P6. Two control predictions did not hold on the **planned** runs:
- **P4** (original template with cache ≈ fixed template without cache) came out at 1.117. That missed its predicted 0.9–1.1 band, though it stayed inside the falsification bounds.
- **P5** (removing the header without a cache gives no gain; falsified below 0.9) came out at 0.895. **P5 was falsified.**

**Post hoc runs.** Two extra cache-off runs were added *after* that analysis was read. They moved the values to 1.091 and 0.917, but they're post hoc and change neither verdict.

**Excluded runs.** 4 of the 17 runs failed the 10 ms send-lag check and are excluded. All 4 were outside the headline comparison.

## 8. Trade-offs and limitations

- **CPU, not GPU.** The milliseconds don't transfer to Relay's GPU fleet. The cache share may not transfer unchanged either: vLLM caches fixed-size blocks, evicts under memory pressure and uses the real model's tokenizer.
- **Synthetic weights.** No quality claim is possible.
- **One user's session at a time on a one-slot server.** No eviction, concurrent users or multi-replica routing. The editing-session shape is assumed, not fitted to Relay data.
- **Small samples.** 48 requests per run and 3 runs per configuration, so p99 supports no conclusion. The run-and-session bootstrap interval (0.18–0.24 for the paired ratio) is only a rough bound ([ticket write-up](README.md#uncertainty)).
- **Partly unexplained.** With the original template, cache on was about 9% *slower* than cache off. The 43 header tokens explain part of that; the rest is unexplained.
- **Trade-off of the fix.** Anything that read the request ID from the prompt must read `X-Request-Id` instead.
- **Outstanding:** a fresh, preregistered confirmation run on a quiet machine, and re-measurement on a GPU with vLLM.

## 9. What I'd do next

1. **Confirmation run.** Preregister and run a fresh confirmation of the full 15-run plan on a quiet machine.
2. **GPU re-measurement.** Re-run the same traces and template switch on vLLM with a GPU, using vLLM's own prefix-cache metrics (`gpu` source).
3. **Many users.** Interleave many users' sessions on a multi-slot server to measure the hit share under eviction, then decide whether replicas need prefix-aware routing.
4. **Sliding windows.** Test editors that send a sliding window of code, which changes the prompt's start on every keystroke the same way the header did.

## 10. Interview explanation (about 75 seconds)

> In this case study, a fictional customer reports that turning on prefix caching changed nothing. The bug is planted by design; my work was proving the cause and measuring the fix. A prefix cache only reuses tokens up to the first point where two prompts differ, so my hypothesis was the per-request header at the very top of every prompt: a request ID and a timestamp, which made every prompt unique within about ten tokens.
>
> I tested it on a real inference engine, llama.cpp on CPU, because our simulator doesn't model caching. I replayed the same editing-session trace against four configurations: original or fixed template, with the cache on or off. I added a negative control where context never repeats, and wrote down my predictions and failure thresholds before reading any results.
>
> With the header in place, the engine reused half a percent of prompt tokens. With the header moved into an HTTP header, it reused 83%, and median time to first token dropped from about 2.5 seconds to about 0.65 seconds. The cache-off control confirmed the cache was doing the work.
>
> Two control predictions didn't hold, and I report that. It's CPU with synthetic weights, so the next step is confirming it on a quiet machine and re-measuring on GPUs with vLLM.
