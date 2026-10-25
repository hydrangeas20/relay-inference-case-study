# RLY-4 independent review (PR #3, head `f86deca`)

The headline finding survives. The control claims and the CI failure did not survive as written; both are corrected in this branch. Every number here comes from [`recompute.py`](recompute.py), which shares no code with `analyze.py`. Its full output is in [`recompute-output.txt`](recompute-output.txt).

## What was recomputed

- **Inputs:** raw per-request records, llama.cpp counters scraped before and after each run, and the load generator's raw send times.
- **Run validity:** recomputed from raw send times. It agrees with the committed summaries on all 17 runs: 13 valid, 4 invalid.
- **Cache share:** two independent telemetry sources agree exactly in every run:
  - the per-request `cache_n` and `prompt_n` in the final SSE chunk;
  - the server's `llamacpp:prompt_tokens_cached_total` and `llamacpp:prompt_tokens_total` counters.

  The denominator is the full prompt length (`cache_n + prompt_n`).
- **Output length:** identical everywhere, exactly 8 tokens on every request in every run.
- **Prompts:**
  - Original prompts are exactly 60 characters and 43 tokens longer than fixed ones, on every request. That is the header and nothing else.
  - Fixed prompts with cache on and with cache off have identical token counts.

## The headline, three ways

| Aggregation | Original → fixed | Speed-up |
| --- | --- | --- |
| Ratio of median per-run p50s (the README's "3.9x") | 2,524 → 654 ms | 3.86x |
| Ratio of pooled p50s | 2,554 → 657 ms | 3.89x |
| Median of paired per-request ratios | 0.217 (95% CI 0.188–0.234, session bootstrap) | 4.6x (4.3–5.3x) |
| Ratio of median per-run p95s (the README's "2.9x") | 5,799 → 2,013 ms | 2.88x |
| Server-side prefill time per request (no queueing), paired median | 0.239 | 4.2x |

**Verdict on the headline:** "3.9x" is correctly computed, and it is the most conservative of the three aggregations. The README now says which aggregation it is. No invalid run belongs to the two headline conditions, so the result doesn't depend on the exclusions.

## Findings and fixes

| # | Severity | Finding | Fix in this branch |
| --- | --- | --- | --- |
| 1 | High | "All six predictions held" was false under the planned design. P5 was falsified on the planned runs (0.895 < 0.9), and P4 missed its predicted band (1.117). Two extra cache-off runs were added **after** that analysis was read; they moved both inside their bands. That is selective replication. The independent controls, which also lost a run, got no extras | Ticket, README and PR description report planned and post hoc values separately. P5 is marked falsified; P4 as missing its band |
| 2 | High | CI `check` failed on 2 of 3 attempts (`64dcf8f` attempt 1; head `f86deca`), both in the pytest step. The logs couldn't be retrieved from this environment, so **the CI root cause is unconfirmed** | Reproduced locally. Under 2-core contention, `test_end_to_end` failed 3 of 23 times at the PR head, every time on the 10 ms send-lag gate this PR introduced. The base commit failed 0 of 15 under the same load. The functional test no longer requires the host to meet a measurement bar (the gate itself is unchanged and unit-tested). Fixed version: 0 failures in 20 contended runs; full suite 3 of 3 passing under contention |
| 3 | Medium | Wrong figures in the write-up: header "~25 tokens" (actually 43); prompts "1,400–1,800 tokens" (actually 1,470–2,400, median 1,780); follow-ups evaluate "20–55 tokens" (actually 22–135, median 40); prompts diverge "from about the 6th token" (cached prefix is 0, 7 or 10 tokens) | Corrected |
| 4 | Medium | The write-up claimed the cache share transfers to GPU/vLLM. vLLM caches in fixed-size blocks, evicts under memory pressure, and the real model's tokenizer differs | Reworded: it must be re-measured on vLLM |
| 5 | Medium | The smoke workflow's "worker drained the queue" step asserted nothing | The step now fails unless the worker's ok-job counter reaches the number of indexing jobs in the smoke trace |
| 6 | Medium | The README's llama.cpp reproduction commands cloned into the repo, then pointed at `../llama.cpp` | Commands fixed; full commit SHA pinned |
| 7 | Low | The "9% slower with cache on" note offered cache bookkeeping as a cause without evidence | Replaced with what was measured (43 header tokens, plus 6% higher prefill cost per token) and marked unexplained |
| 8 | Low | `server/rep*.cmd` record the sandbox's absolute binary path, and the local verification worker log holds a teardown traceback with sandbox paths. Neither contains credentials or personal data. They're kept unmodified as evidence | The runner now records the binary's name only, for future runs |
| 9 | Low | The worker process exits with an uncaught exception when SQS becomes unreachable (seen at teardown of the local verification) | Not fixed: outside this review's scope. Noted for RLY-7 |
| 10 | Info | Exclusions are rule-based and auditable. The 10 ms rule was committed at 13:54:54, before the first run started (13:55:27). The code applied it to every run, and all 4 excluded runs remain on disk. The invalid runs fell in non-headline conditions (4 of 11 runs there, 0 of 6 in the headline pair); with this few runs, that pattern can't be told apart from chance | None |
| 11 | Info | The predictions were committed at 13:58:29, while the first run was in progress and before any full-run result existed (first summary written 13:59:31). They were informed by a 6-request pilot, which PREDICTIONS.md discloses. P2's 60% threshold sits close to the pilot's 66% | None; the disclosure stands |

## Sensitivity (invalid runs included: non-inferential)

| Comparison | Valid runs only | Including invalid runs |
| --- | --- | --- |
| Fix, paired median ratio | 0.217 | 0.217 (no invalid runs in that pair) |
| P4 original+cache / fixed+no cache | 1.091 | 1.083 |
| P5 fixed+no cache / original+cache | 0.917 | 0.923 |
| Negative control | 0.905 | 0.933 |

## What this experiment does and doesn't show

**It shows:**
- On a real engine with a real prefix cache, the header at the front of Relay's prompt prevents reuse.
- Removing it lets follow-up requests in an editing session reuse most of their prompt.
- That cut server prefill time per request to about a quarter (server-side, queue-free).
- TTFT fell by about 4x on this workload.

**It doesn't show:**
- GPU or vLLM latency, or a GPU cache hit rate.
- Anything about output quality (the weights are synthetic).
- Behaviour with many concurrent users, cache eviction, or multiple replicas.
- Capacity or cost at Relay's scale.

**Remaining confounders:**
- **Queueing.** Part of the TTFT gain comes from shorter queues, because one slot serves everything. The queue-free prefill ratio (0.24) bounds the mechanism alone.
- **Run order and drift.** Runs interleave conditions within each repetition. No CPU frequency or thermal telemetry is available in this VM.
- **Unexplained 9% gap.** The original-template-plus-cache vs cache-off difference remains unexplained.
- **Sessions are assumed.** The workload's session shape is assumed, not fitted.
