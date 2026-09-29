# ADR-0005: Revising the traffic model after the verification audit

- **Status:** Accepted
- **Date:** 2026-09-28
- **Decided by:** hydrangeas20
- **Amends:** [ADR-0004](0004-traffic-model.md)
- **Validation:** [Phase 2 preregistration](../validation/phase-2-preregistration.md) (Amendments 1 and 2). **Outcome:** no candidate passed Thursday; the cycle is closed with Wednesday untouched; see the [queueing diagnosis](../validation/phase-2-queueing-diagnosis.md).

A verification audit of the Phase 2 traffic model (2026-09-28) found that several claims were stronger than the evidence, and that the burstiness model didn't generalise across request rates. This ADR records the decisions that followed. How the revised model is validated is fixed separately, in the preregistration.

## D1. Burstiness depends on request rate

**Evidence (AZURE-DERIVED, all-days audit):** the rate's relative standard deviation falls with the hour's request rate, from about 0.23 at 3–10 rps to 0.105 at 60–120 rps (roughly σ ∝ rate^−0.37). The previous model used one pooled value (0.16).

**Decision:**
- Inside the observed Azure range, σ follows a relationship fitted to the trace's own expected rate.
- Outside the range, burstiness is uncertain and comes from one of three pre-declared scenarios: `edge` (canonical), `poisson` and `trend` (PROJECTED).
- The relationship extrapolated to Relay's modelled full-scale peak (about 2,400 rps) is never presented as an empirical estimate.
- Queueing-sensitive conclusions outside the range are reported under all three scenarios.
- Where interpolation ends and extrapolation begins is documented (preregistration §4).

**Correlation time:** one τ fitted on training data is the baseline candidate (C1). A banded τ is the second candidate (C2). Thursday may choose between them; Wednesday may not.

## D2. Sub-second timestamp structure is scoped out of canonical traffic

**Evidence (AZURE-DERIVED):**
- Across the whole week, almost no arrivals fall in the last ~50 ms of each 250 ms interval.
- Gaps under 1 ms are 6–9× more frequent than random arrivals would give, at every rate.
- The timestamps aren't rounded or duplicated.
- Azure's documentation says TIMESTAMP is "invocation time" from "a subset of invocations," but not where it's recorded or how the subset was drawn.

These timestamp semantics are **insufficient to determine** whether the structure reflects traffic behaviour or the collection or serving pipeline.

**Decision:**
- Canonical Relay traffic doesn't reproduce the 250 ms structure or the excess sub-millisecond clustering.
- A separate `clustered` sensitivity variant represents excess clustering *without* the 250 ms periodic pattern.
- Canonical traffic is judged against Azure timestamps de-jittered within each 250 ms interval. Raw Azure is compared with the clustered variant descriptively only.
- A question is prepared for the dataset maintainers (`docs/validation/azure-maintainers-question.md`); Phase 2 doesn't wait for the answer.

## D3. Queueing acceptance test

Adopted as preregistered (§7): 96 cells (24 held-out hours × two service times × two utilisations), 20 seeds, a Poisson control, and the near-zero rule. The thresholds (p95/p99 ratio 0.67–1.5 in ≥ 80% of cells, none outside 0.5–2.0, beating Poisson in ≥ 80%) are engineering acceptance thresholds chosen before evaluation, not values established by Azure or the literature.

## D4. Out-of-sample validation

Training Fri–Tue, validation Thu, holdout Wed, plus rate-band holdouts. Tolerances are 2× the training days' day-to-day spread, computed on Fri–Tue only. Wednesday isn't pristine: it contributed to the earlier all-days pooled audit. No Wednesday-specific result has been inspected, and no revised model is tuned against it.

## D5. Prompt-size fidelity

- The generator becomes template-aware: it builds each completion prompt to its target size where Relay's template can represent it.
- The gateway measures every built prompt.
- The built distribution, not the target distribution, is validated.
- Targets below the template's minimum are **kept and flagged**, never resampled. The fidelity claim is conditional on representable targets.
- 3.5 characters per token is a temporary stand-in until Phase 3's tokenizer.

## D6. Claim labels

Every quantitative claim in Phase 2 documentation carries one label (defined in `docs/methodology.md`): ASSUMED, AZURE-DERIVED, CALCULATED, MEASURED, SIMULATED or PROJECTED. Synthetic traffic is never described as "matching Azure" without naming the statistic, the rate range and the validation procedure.

## D7. Trace identity

Three separate identities:
- `spec_id`: the requested workload specification plus its input data hashes.
- `generator_sha256`: the implementation and environment that generated the trace.
- `trace_id`: the content-addressed hash of the generated requests.

## D8. Reproducible evidence

The audit and validation scripts live in `analysis/`, run locally from the SHA-256-verified raw dataset, and commit derived results with that hash. The raw dataset (~690 MB) isn't committed.

## D9. If the holdout fails

The failure is recorded. There's no tuning, threshold change, model change or rerun against Wednesday. A failure becomes a documented limitation that constrains Phase 2's claims. A subsequent revision is a new validation cycle, and must acknowledge that this Azure week no longer contains an unused holdout.

## Merge gate

Phase 2 stays unmerged until the preregistered Wednesday evaluation has been run exactly once and its result, pass or fail, has been documented and reviewed. A pass supports the preregistered out-of-sample claim. A failure limits the claim; it isn't grounds for changing the test after seeing the result.
