# RLY-1: "Completions feel sluggish at peak"

| | |
|---|---|
| **Theme** | Batching and concurrency |
| **Status** | Planned |
| **Results source** | `gpu` (per-GPU curves), `sim` (at scale) |

## Customer complaint

> "Mornings are bad. It's fine at 7 a.m. and terrible by 10."

## Root cause (planted)

The server's maximum concurrent requests (`max-num-seqs` in vLLM) is set far too low. Requests queue at peak even though the GPU has spare capacity.

## Reproduce

1. Deploy with the low concurrency limit.
2. Ramp request rate in steps and record p50/p95/p99 TTFT at each step.
3. Show p95 TTFT crossing the SLO while GPU utilization and KV cache usage are still well below saturation.

## Fix

- Sweep concurrency and batching settings.
- Find the setting that maximizes goodput (requests/sec meeting SLO) without pushing ITL past acceptable levels. Raising concurrency too far trades TTFT for slower token generation.

## Acceptance criteria

- [ ] Latency vs. request rate curves (p50/p95/p99) for before and after, same traffic trace.
- [ ] Sustainable request rate at SLO, before vs. after, reported per GPU.
- [ ] The chosen setting is justified against at least two alternatives, including one that's too aggressive.

## Proof

Latency vs. request rate chart, before/after, with the SLO line. The knee in the curve moves right.

## Connects to

Raises capacity per GPU, which RLY-3's cost calculation depends on.

---

## Findings

*Filled in once the ticket has been worked. Every number links to its file in `results/`.*

### Diagnosis

### What changed

### Before / after

| Metric | Before | After | Source |
|---|---|---|---|

### Recommendation to Relay

### What I'd do with more time
