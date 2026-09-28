# Phase 2: Traffic model

**Goal:** traces that behave like Relay's real traffic: a realistic daily shape, realistic burstiness and realistic request sizes, at a scale one GPU or the simulator can run.

Decisions: [ADR-0004](../decisions/0004-traffic-model.md).

## Acceptance criteria

Revised after the 2026-09-28 verification audit ([ADR-0005](../decisions/0005-traffic-model-revision.md)). Validation follows the [preregistration](../validation/phase-2-preregistration.md).

- [x] Weekday envelope with every assumption in one config file, each marked with a claim label
- [x] Envelope's peak/trough ratio falls inside Azure's training-weekday range, checked by `make traffic-check` (a plausibility check; peak-to-mean isn't checked)
- [x] Burstiness depends on request rate, fitted on training days with reproducible scripts (`analysis/`, from the SHA-256-verified raw trace)
- [x] Outside Azure's observed rate range, traces need an explicit scenario (`edge`, `poisson` or `trend`), recorded in the header
- [x] Generated traffic reproduces the training bands' curves in-sample (`make traffic-check`; shows the generator implements the fit, not validation)
- [ ] Out-of-sample band checks and band holdouts pass on Thursday (blocked on preregistration open items O1 and O2)
- [ ] Queueing test passes on Thursday and beats Poisson (blocked on O1 and O2)
- [ ] C1 or C2 chosen by the preregistered selection rule (blocked on O1 and O2)
- [ ] Wednesday holdout evaluated exactly once, and the result documented and reviewed (not yet authorised)
- [x] Canonical traffic has no 250 ms pattern; a `--clustered` variant exists for sensitivity runs
- [x] Completion target sizes resampled from Azure training days; each request records its target sizes
- [x] Built prompts follow the target distribution for representable targets (KS 0.006 vs critical 0.013; MEASURED at the gateway); below-minimum targets kept and flagged (5.6%)
- [x] Day and window traces, scaled by one parameter; header records the scale and daily-active-user equivalents
- [x] Trace format v3: `spec_id`, `generator_sha256` and a content-addressed `trace_id` checked on read; v1 and v2 traces still read
- [x] Same spec and seed produce a byte-identical trace
- [x] Azure-derived files carry CC-BY attribution
- [ ] Day traces can be replayed (blocked on Q11 in ADR-0004)

## Merge gate

Phase 2 stays unmerged until the preregistered Wednesday evaluation has been run exactly once and its result, pass or fail, has been documented and reviewed. A pass supports the preregistered out-of-sample claim. A failure limits the claim; it isn't grounds for changing the test after seeing the result.

## Deferred

The results schema originally planned for this phase needs its own decisions (file format, how before/after runs are grouped). Those come next, before Phase 3.

## Verification

`make check` (111 tests) and `make traffic-check` (in-sample only):

```
envelope: PASS
  peak/trough 9.64x (CALCULATED); Azure training weekdays 8.61x-11.29x (AZURE-DERIVED)
  smooth-curve peak 2434 interactive rps (CALCULATED)
burstiness C1: sigma = 0.4407 * rate^-0.3231 within 3.2-82.83 rps (AZURE-DERIVED, training days)
  in-sample: generated (mean of seeds) vs training pooled curve, windows [1, 2, 5, 10, 30, 60]
    3-10 rps at   7.66: max |diff| 0.0207  PASS (tolerance 0.0985)
   10-30 rps at  15.17: max |diff| 0.0115  PASS (tolerance 0.0321)
   30-60 rps at  48.54: max |diff| 0.0069  PASS (tolerance 0.0146)
  60-120 rps at  70.75: max |diff| 0.0062  no tolerance (pending O2)
```

Out-of-sample results go in `analysis/results/validation-*.json` as they're run.
