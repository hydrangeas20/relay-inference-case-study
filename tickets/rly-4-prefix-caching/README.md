# RLY-4: "We turned on prefix caching. Nothing changed."

| | |
|---|---|
| **Theme** | KV cache reuse |
| **Status** | Planned |
| **Results source** | `gpu` |

## Customer complaint

> "We enabled prefix caching like the docs said. Nothing changed."

## Root cause (planted)

Relay's prompt template puts a timestamp and request ID at the **top** of the system prompt. Every prompt starts differently, so the cache almost never hits.

## Reproduce

1. Send completions traffic using Relay's prompt template with prefix caching enabled.
2. Show the near-zero cache hit rate from server metrics.

## Fix

- Reorder the template: stable content first (system prompt, repo context), variable content last.
- Re-run the same traffic.

## Acceptance criteria

- [ ] Cache hit rate before and after, from server metrics.
- [ ] TTFT distribution (p50/p95/p99) before and after, same traffic trace.
- [ ] The diagnosis explains *why* the hit rate was near zero, not just that it was.

## Proof

TTFT distribution before/after, and cache hit rate over the run.

## Connects to

The largest single TTFT win, which relieves pressure on RLY-1.

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
