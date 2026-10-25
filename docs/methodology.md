# Methodology

Inference benchmarks are easy to get wrong in ways that look convincing. These rules exist so that every number in this repo can be defended.

## 1. Every result says where it came from

Every results file carries a `source` field:

| `source` | Meaning |
|---|---|
| `gpu` | Measured on a real GPU running the real model |
| `cpu` | Measured on a real inference engine running on CPU (ADR-0007). Real caching and scheduling behaviour; not GPU latency. With RLY-4's synthetic-weight model, no quality signal |
| `sim` | Measured against the calibrated simulator |
| `projection` | Computed from a capacity model (e.g. Vidur, or arithmetic from measured per-GPU capacity) |
| `floci` | Measured on the emulated AWS plumbing, with no inference in the path |

Charts and write-ups label the source wherever a number appears. A `sim` or `projection` number is never presented as a measurement.

### Claim labels in documentation

Every quantitative claim in the docs carries one of these labels (ADR-0005, D6):

| Label | Meaning | Example |
|---|---|---|
| ASSUMED | A scenario input the project chose | 400K daily active users |
| AZURE-DERIVED | A statistic computed from Azure's public trace | Median prompt 1,930 tokens |
| CALCULATED | Arithmetic from other labelled values | 102.4M requests/day |
| MEASURED | Observed by running Relay's own code or system | Built prompt sizes reported by the gateway |
| SIMULATED | A property of synthetic traffic or a simulated queue | p99 wait in the queueing test |
| PROJECTED | A value outside the range of the data it's based on | σ under the `trend` scenario at 2,400 rps |

These are for claims in prose. The `source` field above tags result files, and maps onto them: `gpu`, `sim` and `floci` results are MEASURED on the respective system; `projection` results are PROJECTED or CALCULATED.

## 2. Quality claims come only from real models

The simulator models latency and throughput, not output quality. Any claim that a change "didn't hurt quality" must be backed by an eval run on a real GPU with the real model, with results tagged `gpu`.

## 3. The simulator is calibrated, and the calibration is checked

The simulator's latency parameters are fitted to real GPU measurements (Phase 3). Calibration is checked by replaying the same traffic against both and comparing p50/p95/p99 TTFT and throughput. The calibration error is reported, and conclusions that depend on differences smaller than that error aren't drawn.

## 4. The load generator must not be the bottleneck

A slow client makes a fast server look slow. Every load test run must:

- **Be open-loop.** Requests are sent on a schedule (e.g. Poisson arrivals at the target rate) regardless of whether earlier ones have completed. Closed-loop generators hide overload instead of revealing it.
- **Self-check.** Log the generator's intended vs. achieved send rate, each request's send lag (actual minus scheduled send time) and the generator's CPU usage. The run is **invalid** if achieved rate falls more than 2% short of intended, if send-lag p99 exceeds 10 ms, or if the generator's CPU is saturated. Invalid runs are kept and reported as invalid, never used as results. The send-lag rule exists because the rate check compares averages: a generator that falls behind during a burst and catches up afterwards passes it while delaying exactly the requests that form the tail.
- **Scale out when needed.** High-volume simulator runs use several generator processes.

### What TTFT measures, layer by layer

| Layer | Clock starts | Clock stops | Includes |
|---|---|---|---|
| Client (load generator) | Just before the HTTP request is sent, at its scheduled time | First SSE line carrying generated text | Connection setup if no pooled connection is free, gateway prompt building, gateway-to-server hop, server queueing, prefill, first decode step |
| Gateway (`relay_gateway_upstream_ttft_seconds`) | Request received, before the upstream call | First upstream line carrying generated text | Upstream connection, server queueing, prefill, first decode step |
| Server (`vllm:time_to_first_token_seconds`) | As defined by the engine | As defined by the engine | Engine-internal. llama.cpp doesn't export this histogram; its per-request `prompt_ms` (prefill time) is recorded instead |

SLOs are judged on client samples, the only layer that matches what a user waits for. Server-side histograms are coarse (vLLM-style buckets jump from 0.25 s to 0.5 s), so they can only cross-check, not resolve, a 300 ms target.

## 5. Before and after means same traffic

A before/after comparison replays the **same traffic trace** (same seed, same arrival times, same prompt/output length distributions) against both configurations. Only one thing changes between the two runs.

## 6. Percentiles, not averages

Latency is reported as p50, p95 and p99. Averages hide exactly the tail that users complain about (see RLY-0).

## 7. Repetition and variance

GPU runs are repeated at least 3 times per configuration. Results report the median and the spread across runs. A difference smaller than run-to-run variance isn't called an improvement.

## 8. Results are data, charts are generated

Every run writes a JSON file to `results/` following the schema defined in Phase 2. Every chart on the case study site is generated from those files, never drawn by hand. Re-running an experiment updates its chart.

## Metrics glossary

| Metric | Definition |
|---|---|
| TTFT | Time to first token: request sent → first output token received |
| ITL | Inter-token latency: time between consecutive output tokens |
| E2E latency | Request sent → final token received |
| Throughput | Output tokens per second, across all requests |
| Goodput | Requests per second that meet their SLO |
| Cost per 1K requests | GPU $/hour ÷ requests served per hour at SLO × 1000 |
