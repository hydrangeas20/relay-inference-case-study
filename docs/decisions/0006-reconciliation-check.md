# ADR-0006: How the three TTFT layers are reconciled

- **Status:** Accepted (approved by hydrangeas20, 2026-09-29). Implemented in `da57184`.
- **Date:** 2026-09-29
- **Amends:** [ADR-0003](0003-phase-1-foundation.md) §3, the rule only. Measuring at three layers and reconciling them is unchanged.

## Context

ADR-0003 §3 says an outer layer (client ⊃ gateway ⊃ server) must never be faster than an inner one "beyond the inner histogram's bucket width". `reconcile.py` implemented that by comparing p50, p95 and p99 of each pair, with the inner bucket width as the tolerance.

GitHub Actions failed `test_end_to_end.py::test_replay_is_valid_and_reconciles` with client p99 64.8 ms and gateway p99 90.8 ms against a 25 ms tolerance. Diagnosis (summary in the [Phase 2 page's CI note](../phases/phase-2-traffic-model.md#ci-note-reconciliation-false-alarm-2026-09-29); the reproductions were run outside the repo and aren't committed):

- **Measurement is correct.** The gateway's interval (request parsed → first upstream content line, before forwarding) lies strictly inside the client's (task start → first content line received), on the same monotonic clock. Across 3,330 requests matched by request ID, under idle, CPU-contended and stall-injected conditions, the client's TTFT was never below the gateway's (smallest gap +1.10 ms).
- **The comparison is wrong.** Comparing quantile to quantile compares two different estimators:
  - The gateway's is interpolated inside a Prometheus bucket. The buckets near 90 ms are 75–100 ms, and 90.8 ms is exactly what one sample in that bucket out of 37 produces.
  - The client's is numpy's interpolation between its two slowest exact samples.
  - With n = 37, p99 is decided by the slowest one or two requests. One request delayed by a CI scheduling stall inside the gateway's interval makes the two estimates diverge by more than the tolerance, even though every request nested correctly.
  - In a Monte Carlo with nesting guaranteed by construction, the old rule flagged 23–33% of runs. Under injected process freezes it flagged 12 of 30 runs.
- **The old rule also misses real violations.** A client faster than the gateway on a single request in the tail barely moves p50, p95 or p99.

## Options considered

1. **Keep quantile comparison with a wider tolerance.** Simple, but it hides the design error, still produces false alarms at small n, and still can't see tail violations.
2. **Match requests by ID.** This is the exact check. The gateway would have to export per-request timings: a new interface, and new data to store and scrape.
3. **Stochastic dominance at shared bucket bounds.** Per-request nesting implies count(outer ≤ b) ≤ count(inner ≤ b) at every bucket bound b both layers share. This holds exactly, needs no tolerance, works at any sample size, and still holds when the inner layer sees extra traffic. The client's exact samples are counted at the inner histogram's bounds.

## Decision

Option 3. Quantiles are still reported for reading, but aren't compared. The end-to-end test also states the invariant directly: it records the gateway's TTFT values in-process and asserts that the k-th fastest client TTFT is never below the k-th fastest gateway TTFT.

## Consequences

- No false alarms from bucket interpolation or small-n tails. A disagreement is a real inconsistency at bucket resolution.
- It detects a violation only when it crosses a shared bucket bound. A client faster than the gateway by less than the gap to the next bound goes unseen. Option 2 would close that gap if it ever matters.
- ADR-0003's Q2 (what to do about a disagreement) and Q3 (acceptable client–server gap) are unchanged and still open.
