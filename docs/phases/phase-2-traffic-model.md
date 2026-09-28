# Phase 2: Traffic model

**Goal:** traces that behave like Relay's real traffic: a realistic daily shape, realistic burstiness and realistic request sizes, at a scale one GPU or the simulator can run.

Decisions: [ADR-0004](../decisions/0004-traffic-model.md).

## Acceptance criteria

- [x] Weekday envelope with every assumption in one config file, marked as assumption or Azure-derived
- [x] Envelope's peak/trough ratio falls inside Azure's weekday range, checked by `make traffic-check`
- [x] Burstiness fitted from Azure data with a reproducible script (`analysis/azure_traffic.py`)
- [x] Generated traces reproduce the fitted burstiness at 1–60 s windows (within 0.03)
- [x] Completion sizes resampled from Azure; each request records its target sizes
- [x] Prompt shortfall against targets is measurable
- [x] Day and window traces, scaled by one parameter; header records the scale and users represented
- [x] Same spec and seed produce a byte-identical trace
- [x] Trace format v2 still reads v1 traces
- [x] Azure-derived files carry CC-BY attribution
- [ ] Day traces can be replayed (blocked on Q11 in ADR-0004)

## Deferred

The results schema originally planned for this phase needs its own decisions (file format, how before/after runs are grouped). Those come next, before Phase 3.

## Verification

`make check` (67 tests) and `make traffic-check`:

```
envelope: PASS
  peak/trough 9.64x (Azure Mon-Thu 9.13x-11.29x)
burstiness (relative rate fluctuation by window):
    1s  generated 0.155  Azure 0.155  PASS
   10s  generated 0.133  Azure 0.133  PASS
   60s  generated 0.081  Azure 0.081  PASS
```
