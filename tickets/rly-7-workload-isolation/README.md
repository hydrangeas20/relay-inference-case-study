# RLY-7: "Nightly indexing is slowing down daytime users"

| | |
|---|---|
| **Theme** | Batch vs. interactive isolation |
| **Status** | Planned |
| **Results source** | `sim`, `floci` |

## Customer complaint

> "Some mornings everything is slow, and it clears up by noon."

## Root cause (planted)

Repository sizes tripled. The nightly embedding job now overruns into business hours and competes with interactive traffic on shared infrastructure.

## Reproduce

1. Enqueue a large indexing backlog into SQS (Floci) that runs into the morning ramp.
2. Show interactive p95 TTFT degrading while the batch job runs.

## Fix

- Move indexing to its own deployment.
- Drain the queue with backpressure (bounded in-flight requests).
- Schedule the job so it can't collide with peak hours, with an alert if it's projected to overrun.

## Acceptance criteria

- [ ] Interactive p95 TTFT during the batch window, shared vs. isolated, same traffic.
- [ ] Indexing completion time before and after.
- [ ] Overrun alert fires in a test where the backlog is too large to finish in time.

## Proof

Interactive p95 over the night-to-morning window, shared vs. isolated.

## Connects to

Shows workload isolation and uses the customer-side AWS plumbing.

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
