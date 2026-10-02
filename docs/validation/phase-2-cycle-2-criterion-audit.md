# Phase 2, Cycle 2: criterion-audit results and a proposed criterion revision

- **Date:** 2026-10-02
- **Status:** Audit complete. **Decision: STOP** (preregistration section 7). The revision in section 4 is **PROPOSED, not adopted.** No candidate has been fitted.
- **Order of events:**
  1. `196074a`: preregistration skeleton, which fixed the audit procedure and thresholds
  2. `e756c05`: audit implementation, committed before it ran
  3. the run
  4. the aggregate analysis of the null, written after the audit result was seen
- **Data:** the six development days only, read through the cache-only guard. **Wednesday was not accessed.** No raw file was opened.
- **Outputs:**
  - `analysis/results/cycle2/criterion-audit.json` (every per-cell metric)
  - `criterion-audit-aggregate.json`
  - reproduce with `uv run python analysis/criterion_audit.py` (about 30 minutes on 2 cores), then `analysis/cycle2_null_aggregate.py`

## 1. Result against the preregistered decision rule

**N1, self-consistency.** The "model" *is* the truth process: the median of 20 realisations, compared with 50 further realisations, each playing Azure.

| Truth process | P(3-of-4 rule passes) | Folds passing all three criteria | Criterion 1 (≥ 80% of cells in 0.67–1.5×) | Criterion 2 (no cell outside 0.5–2.0×) | Criterion 3 (beats Poisson) | Catastrophic false alarm (per fold) |
|---|---|---|---|---|---|---|
| Cycle 1 C1 | **0.00** | 0% (every fold) | 0–2% of replicates; median 59–63 of 96 cells in band | 0%; median 15.5–19.5 cells out | 100% | **92–100%** |
| Bootstrap | **0.00** | 0% | 0%; median 60–63 cells in band | 0%; median 15.5–19 cells out | 100% | **94–100%** |

**N2, Azure vs Azure** (real Azure against the bootstrap from the other five days): **fails in all four folds.**
- In band: 59, 63, 58 and 51 of 96 cells, against 77 required.
- Out of bounds: 20–25 cells.
- Catastrophic cells: 6–10 per fold.

**Decision, preregistered in section 7:** P_rule < 0.80 for both truth processes, and catastrophic false alarms above 0.05, so **STOP: the rule is poorly calibrated under the self-consistency null.**

## 2. Why: per-cell, per-hour comparisons measure sampling noise

The null is **unbiased**: the median model/reference ratio is 0.97–1.02 in every cell type, for both truth processes. But one hour is one realisation, and its p95/p99 wait is very noisy:

| Cell (C1 truth; bootstrap within ±0.05) | Ratio, 10th–90th percentile | Share within 0.67–1.5× | Share outside 0.5–2.0× |
|---|---|---|---|
| s 0.2, ρ 0.6, p99 | 0.74–1.24 | 0.91 | 0.03 |
| s 0.2, ρ 0.8, p99 | 0.48–1.80 | 0.60 | 0.18 |
| s 1.0, ρ 0.6, p99 | 0.41–1.62 | 0.62 | 0.19 |
| s 1.0, ρ 0.8, p99 | 0.49–1.84 | 0.57 | 0.18 |

At 80% utilisation, a perfect model lands outside 0.5–2.0× in about one cell in six. A fold has 192 cell-metrics, so "no cell outside 0.5–2.0×" fails almost surely, and "≥ 80% in 0.67–1.5×" can't be met when the in-band rate is about 60%. Criterion 3 is a comparison against Poisson within the same cell, and it isn't affected.

**Bearing on Cycle 1 (history unchanged).** Cycle 1 used the same per-cell criteria on one day. A perfect model would have failed them too, so Cycle 1's pass/fail verdict on criteria 1–2 couldn't discriminate a good model from a bad one. Cycle 1's *recorded* result stands as written. Its diagnosis rests on aggregate evidence and is not affected:
- medians over hours: C1 at 1.29–1.31× Azure on training days and 1.16–1.47× by cell on Thursday, while the null median is 1.00;
- the surrogate experiments.

I suggest adding a dated note to the Cycle 1 record after review.

**N2 is a weak instrument as built.** The bootstrap sits above Azure in 30 of 32 aggregate comparisons. In 23% of seconds it needed the superposition approximation (target rate above source rate), which adds noise. So N2's failure doesn't cleanly separate "criteria unattainable" from "instrument biased".

## 3. What the null supports instead: aggregate over the fold's hours

**Fold statistic:** for each cell (s, ρ) and metric (p95, p99), G = the geometric-mean model/reference ratio over the fold's informative hours. That's 8 values per fold. Averaging 24 independent hours cuts the noise roughly fivefold.

**Null (perfect model).** P(3-of-4 folds have all 8 G within [1/B, B]):

| Bound B | 1.15 | 1.20 | 1.25 | 1.30 | **1.35** | 1.40 |
|---|---|---|---|---|---|---|
| Truth C1 | 0.06 | 0.16 | 0.42 | 0.70 | **0.88** | 0.94 |
| Truth bootstrap | 0.08 | 0.30 | 0.62 | 0.86 | **0.94** | 1.00 |

Other null properties:
- Max |G| per fold, 95th percentile: 1.47× (C1) and 1.43× (bootstrap).
- No fold has any G beyond 2× (0 of 200 per truth).
- One-sided near-zero cells: mean 1.3–1.4% per fold, max 4.7%.

**Power** (synthetic bias injected into the null model; candidate-independent). Each entry is P(3-of-4 rule passes at B = 1.35); lower is better detection.

| Injected bias | Truth C1 | Truth bootstrap |
|---|---|---|
| None | 0.88 | 0.94 |
| ×1.15, all cells | 0.84 | 0.76 |
| ×1.25, all cells | 0.44 | 0.38 |
| ×1.3, ρ 0.8 only | 0.30 | 0.20 |
| ×1.5, all cells | 0.00 | 0.00 |
| ×1.5, s 1.0 / ρ 0.8 only | 0.00 | 0.00 |
| ×0.67, all cells | 0.00 | 0.00 |

**The resolution limit, a property of the data rather than the test:** with one Azure realisation per hour and 24 hours per fold:
- biases of about 1.15× are indistinguishable from noise;
- about 1.25–1.3× is detected roughly 55–80% of the time;
- 1.5×, even if confined to one cell, is detected essentially always.

Any Cycle 2 claim should be worded to match: "no detectable p95/p99 bias beyond about 1.3–1.5×".

## 4. Proposed prospective revision (for review; justified solely by sections 2–3)

The proposal replaces Cycle 1 criteria 1 and 2 *for Cycle 2's internal validation and its Wednesday test*. Criterion 3 and everything else stay unchanged.

| | Current (frozen) | Proposed |
|---|---|---|
| Criterion 1 | ≥ 80% of 96 cells with p95 and p99 ratio in 0.67–1.5× | **C1′:** all 8 fold-level geometric-mean ratios G (4 cells × p95, p99) within **[1/1.35, 1.35]** |
| Criterion 2 | No cell outside 0.5–2.0× | **C2′ (safety):** no G outside **[0.5, 2.0]** in any gating fold. This is the old bound, applied at the level where the null is calibrated (null false-alarm rate 0.000) |
| Near-zero | Per cell | Hours with both values near zero are non-informative. **One-sided near-zero hours ≤ 10% of a fold's cell-metrics** (null max 4.7%) |
| Criterion 3 | Clarified rule, ≥ 80% of informative cells | **Unchanged** (null pass rate 100%) |
| Catastrophic bound | Any cell outside 0.25–4.0× | **Dropped.** Per cell, it can't be calibrated (the null exceeds it in 92–100% of folds). C2′ takes its role |
| Internal rule | ≥ 3 of 4 gating folds pass, no catastrophic cell | ≥ 3 of 4 gating folds pass C1′, criterion 3 and the near-zero cap; **no** gating fold violates C2′ |

**Why B = 1.35.** It's the smallest bound on the preregistered-style grid at which a perfect model passes the rule at least 80% of the time under *both* truth processes (0.88 and 0.94). B = 1.30 fails under the C1 truth (0.70).

**Two follow-ups recommended before freezing** (both candidate-independent):
1. **Rerun N1 with R = 200** to tighten the Monte-Carlo error. At R = 50, the uncertainty on 0.88 is about ±0.05. Freeze B as the smallest grid value with a lower 95% confidence bound ≥ 0.80.
2. **N2:** either rebuild the bootstrap so it never needs superposition (draw sources only from hours at or above the target rate, including the adjacent band), and rerun it under C1′/C2′; or demote N2 to report-only. With the current instrument, aggregated N2 passes Mon (1.09×) and Tue (1.22×) and fails Fri (1.43×) and Thu (1.50×).

## 5. Questions for the owner

1. **Adopt the aggregated form (C1′/C2′),** reject it, or ask for an alternative? Rejecting it means no Cycle 2 candidate can pass internal validation, since even a perfect model can't.
2. **The bound:** accept 1.35 provisionally, pending the R = 200 confirmation (follow-up 1)?
3. **N2:** rebuild the bootstrap and keep N2 as a gate, or demote it to report-only?
4. **Is 80% the right standard** for how often a perfect model must pass the internal gate? It's preregistered, but this is the first time it has bound.
5. **The dated note on Cycle 1's record** (section 2): add it as part of the amendment?
