# Phase 2: Traffic model

**Goal:** traces that behave like Relay's real traffic: a realistic daily shape, realistic burstiness and realistic request sizes, at a scale one GPU or the simulator can run.

Decisions: [ADR-0004](../decisions/0004-traffic-model.md).

## Status (2026-09-29): Cycle 1 closed as a FAILED VALIDATION cycle

*Note (2026-10-03): Cycle 1's per-cell queue criteria 1 and 2 were later found to be uncalibrated to hourly p99 sampling variability, so their failures don't, on their own, show misspecification. The aggregate mismatch and the surrogate findings stand. See the [methodological note](../validation/phase-2-preregistration.md#methodological-note-on-criteria-1-and-2-2026-10-03). Cycle 1 remains failed.*

**The burstiness model is UNVALIDATED.** Cycle 1 ended with no candidate passing. It was stopped by [preregistration Amendment 2](../validation/phase-2-preregistration.md#amendment-2-2026-09-29-after-thursday-validation) and closed by the [Cycle 1 closure](../validation/phase-2-preregistration.md#cycle-1-closure-2026-09-29).

- Training fit: **completed** (C1 and C2, Fri–Tue).
- Thursday validation: **completed**.
- Prompt fidelity: **passed** (representable targets, per-request matched-mixture KS).
- Queue-tail acceptance: **failed** (both candidates fail criteria 1 and 2).
- Candidates validated: **none**. C2 was the selection rule's fallback only.
- Wednesday: **not accessed**. No Wednesday timestamp or statistic has been computed.
- Burstiness model: **UNVALIDATED**.
- Phase 2 infrastructure may merge. **No traffic-model validation claim may be made.**

| | Status | Evidence |
|---|---|---|
| Daily envelope | Plausibility-checked (one ratio, in-sample) | `make traffic-check` |
| Burstiness curve at 1–60 s, out of sample | C2 passed all four Thursday rate bands; C1 failed 30–60 rps. Both passed the rate-band holdouts | `analysis/results/validation-validation.json` |
| **Queue tails (the property that matters for capacity)** | **Failed.** Both candidates fail criteria 1 and 2 (44 and 47 of 96 cells in band; 25 and 27 cells out of bounds). Criterion 3 fails as run (58/87) and passes under the clarified rule (73/87), which doesn't change the verdict | Same file, plus `validation-validation-criterion3-clarified.json` |
| Prompt sizes | Validated for representable targets (per-request, matched-mixture KS) | `validation-prompt-fidelity-amended.json` |
| Trace identity, reproducibility | Tested | `make check` |

- **What remains provisional.** C2 is the selection rule's *fallback* only. It is **not validated** and isn't the default. `traffic/relay.toml` names C1 as the Cycle-1 default, commented as unvalidated. Editing that comment changed `traffic_model_sha256` from `63729ffb…` to `a84d042e…`. Stored Cycle 1 results keep the old hash, which identifies the state they were produced with. Any queueing result generated with either candidate carries this limitation.
- **Why the failure matters.** Both candidates overestimate p99 wait by a median of about 1.3–1.5× at 80% utilisation. So capacity sized on these traces would be conservative, by an amount that isn't known. It's worse with 1 s service times and at high utilisation. For C1 the same overshoot appears on training days (C2 wasn't run there), so it isn't a Thursday artefact. Poisson is far worse in the other direction (about 0.2–0.3×). The bursty model is closer but not good enough to support tail-latency claims.
- **Not tuned away.** No threshold, candidate or parameter was changed after the results were seen. Amendment 2 records the one post-hoc clarification (criterion 3), with both results, and states that it doesn't change the verdict.
- **Wednesday is untouched.** No Wednesday timestamp, token count or statistic has been computed. The loader drops Wednesday lines by date prefix before parsing any field; the only contact with Wednesday bytes is the whole-file SHA-256 check and that prefix filter. It won't be run in this cycle, because no candidate passed Thursday (A2.2). It remains available as the final test for a future cycle.
- **Next investigation (Cycle 2, not started).** The [queueing diagnosis](../validation/phase-2-queueing-diagnosis.md) shows, with surrogate experiments, that the model's per-second count distribution (more right-skewed at 5–10 s) and its time structure at 5–30 s are each sufficient to raise queue tails. Neither is constrained by the fitted 1–60 s variance curve. Chosen direction:
  - **primary:** two-timescale modulation with a lighter-tailed link
  - **secondary:** a Markov-modulated Poisson process
  - **comparator:** a block bootstrap of Azure residuals
  - **salvage experiment:** the existing process fitted to additional higher-order targets

  Cycle 2 treats Thursday as development data and keeps Wednesday as the untouched final lockbox. The [Cycle 2 pre-candidate preregistration](../validation/phase-2-cycle-2-preregistration.md) (2026-10-02) fixes the definitions and decision rules. Its candidate-independent [criterion audit](../validation/phase-2-cycle-2-criterion-audit.md) found that the per-cell queue criteria can't be met even by a perfect model. Cycle 2 is stopped pending review of a proposed aggregated criterion. No candidate has been fitted.

## Acceptance criteria

Revised after the 2026-09-28 verification audit ([ADR-0005](../decisions/0005-traffic-model-revision.md)). Validation follows the [preregistration](../validation/phase-2-preregistration.md).

- [x] Weekday envelope with every assumption in one config file, each marked with a claim label
- [x] Envelope's peak/trough ratio falls inside Azure's training-weekday range, checked by `make traffic-check` (a plausibility check; peak-to-mean isn't checked)
- [x] Burstiness depends on request rate, fitted on training days with reproducible scripts (`analysis/`, from the SHA-256-verified raw trace)
- [x] Outside Azure's observed rate range, traces need an explicit scenario (`edge`, `poisson` or `trend`), recorded in the header
- [x] Generated traffic reproduces the training bands' curves in-sample (`make traffic-check`; shows the generator implements the fit, not validation)
- [x] Open items O1 and O2 resolved by a dated amendment before Thursday (preregistration Amendment 1)
- [ ] Out-of-sample band checks pass on Thursday: **C2 passed all four bands; C1 failed 30–60 rps** (0.0113 vs 0.0102). Both passed the rate-band holdouts
- [ ] Queueing test passes on Thursday and beats Poisson: **both candidates failed** (in band 44 and 47 of 96 cells, needed 77; out of bounds 25 and 27, needed 0; beat Poisson in 58/87 as run, 73/87 under Amendment 2's clarified criterion 3, needed 70)
- [x] Queueing failure diagnosed on training and Thursday data, without tuning ([memo](../validation/phase-2-queueing-diagnosis.md))
- [x] Selection rule applied: no candidate passed; **C2 recorded as the provisional fallback, not validated** (criterion-1 fraction 0.49 vs 0.46)
- [ ] ~~Wednesday holdout evaluated exactly once, and the result documented and reviewed~~ **Superseded for Cycle 1.** Not run: no candidate passed Thursday, so the cycle stopped with Wednesday untouched (Amendment 2, A2.2; Cycle 1 closure)
- [x] Canonical traffic has no 250 ms pattern; a `--clustered` variant exists for sensitivity runs
- [x] Completion target sizes resampled from Azure training days; each request records its target sizes
- [x] Built prompts follow the target distribution for representable targets, judged per request (amended: KS 0.0046 vs critical 0.0131; first, pre-amendment run 0.0060 vs 0.0131; MEASURED at the gateway). Structurally unrepresentable targets kept and flagged (5.6%)
- [x] Day and window traces, scaled by one parameter; header records the scale and daily-active-user equivalents
- [x] Trace format v3: `spec_id`, `generator_sha256` and a content-addressed `trace_id` checked on read; v1 and v2 traces still read
- [x] Same spec and seed produce a byte-identical trace
- [x] Azure-derived files carry CC-BY attribution
- [ ] Day traces can be replayed (blocked on Q11 in ADR-0004)

## Merge gate

**Original gate (historical; superseded for Cycle 1 by Amendment 2):**

> Phase 2 stays unmerged until the preregistered Wednesday evaluation has been run exactly once and its result, pass or fail, has been documented and reviewed. A pass supports the preregistered out-of-sample claim. A failure limits the claim; it isn't grounds for changing the test after seeing the result.

Amendment 2 stopped Cycle 1 without a Wednesday run, so this gate could no longer be met. It no longer governs merging Phase 2.

**Current condition (Cycle 1 closure, 2026-09-29):** Phase 2 may merge as **infrastructure**:
- the traffic generator and the scenario scheme
- trace format v3 and identity
- template-aware prompt sizing and gateway measurement
- reconciliation (ADR-0006)
- the analysis and validation tooling

The burstiness model is merged **UNVALIDATED**. No document, result or summary may claim that Relay's synthetic traffic reproduces Azure's queueing behaviour, or that the traffic model is validated. Queueing results produced with these traces must carry that limitation.

## CI note: reconciliation false alarm (2026-09-29)

`test_end_to_end.py::test_replay_is_valid_and_reconciles` failed on GitHub Actions (client p99 64.8 ms vs gateway p99 90.8 ms, tolerance 25 ms). The measurements were correct. The per-request invariant (client TTFT ≥ gateway TTFT) held for every request in local reproductions, including under injected process stalls. The failure came from comparing a bucket-interpolated histogram p99 with an exact-sample p99 at n = 37, where p99 is set by the one or two slowest requests. It's a reconciliation-design error that CI scheduling stalls trigger.

The fix checks what per-request nesting actually implies (count dominance at shared bucket bounds, with no tolerance), and the end-to-end test now asserts the invariant directly. The rule change is recorded in [ADR-0006](../decisions/0006-reconciliation-check.md), accepted 2026-09-29.

## Deferred

The results schema originally planned for this phase needs its own decisions (file format, how before/after runs are grouped). Those come next, before Phase 3.

## Verification

`make check` (119 tests) and `make traffic-check` (in-sample only):

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

Thursday validation: `analysis/results/validation-validation.json` (criterion 3 clarified: `validation-validation-criterion3-clarified.json`). Queueing diagnosis: `analysis/results/diagnosis-queueing/`. Prompt fidelity: `validation-prompt-fidelity-amended.json` (amended) and `validation-prompt-fidelity.json` (first run, kept). Sensitivity: `sensitivity.json`.
