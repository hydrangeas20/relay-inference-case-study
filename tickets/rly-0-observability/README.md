# RLY-0: "We don't even know what's wrong"

| | |
|---|---|
| **Theme** | Observability |
| **Status** | Planned |
| **Results source** | `sim`, `gpu` |

## Customer complaint

> "Users say it's slow sometimes. Our dashboards show average latency and it looks fine."

## Root cause (planted)

Relay only tracks **average** latency, which hides the slow tail. There are no per-workload, per-token or percentile metrics, so nobody can see which requests are slow or why.

## Reproduce

1. Run mixed traffic (all three workloads) with a bursty arrival pattern.
2. Show Relay's current view: a single average-latency line that looks healthy.
3. Show the same run broken out by workload and percentile, where p99 TTFT is several times the average.

## Fix

- Instrument the gateway and inference layer: TTFT, ITL and E2E latency at p50/p95/p99, throughput, queue depth, running vs. waiting requests, replica count, error rate, all labelled by workload.
- Provision a Grafana dashboard with one row per workload plus an SLO panel.
- Write a short runbook: what to alert on, and why.

## Acceptance criteria

- [ ] Dashboard provisions automatically on `make up` with no manual setup.
- [ ] Every SLO in the client brief has a panel showing current value vs. target.
- [ ] Metrics are identical whether the gateway points at vLLM or the simulator.
- [ ] Runbook defines at least three alerts, each with a threshold and a reason.

## Proof

Side-by-side: Relay's average-latency chart next to the p99 view of the same run. Plus a screenshot of the full dashboard.

## Connects to

Every other ticket. This is how the rest are diagnosed and proven.

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
