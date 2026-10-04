# Phase 2, Cycle 2: criterion-audit results and a proposed criterion revision

- **Date:** 2026-10-02
- **Status (updated 2026-10-04):**
  - The original audit (R = 50, sections 1–5) gave **STOP**: the per-cell criteria are uncalibrated.
  - The aggregated revision was approved **in principle**. It was then tested by a predeclared expanded audit (R = 200, sections 6–7).
  - **Recommended bound: B = 1.40** (section 7.7). The revision is **still PROPOSED: not frozen, not adopted.**
  - No Cycle 2 candidate has been fitted. Wednesday and the raw trace were not accessed.
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

*Superseded in part by section 7 (2026-10-04): the R = 200 audit shows B = 1.35 isn't calibrated at the stated standard. Section 7.7 recommends B = 1.40. The text below is kept as written on 2026-10-02.*

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

---

## 6. Expanded audit: predeclared design (2026-10-03, committed before it runs)

The owner approved the section 4 revision **in principle, not adopted**, and asked for an expanded, candidate-independent audit. Its design is fixed here and in `cycle2_config.AUDIT_EXPANDED` **before it runs**:

- **Replicates:** R = 200 per truth process (Cycle 1 C1 and the within-band bootstrap). Fresh seed entropy (20261003), so the replicates are independent of the original R = 50 audit. The model medians (20 seeds) are also fresh. Same folds, hours, cells and code path: `criterion_audit.py --expanded`.
- **Bounds evaluated, and only these:** B ∈ {1.25, 1.30, 1.35, 1.40}. There's no continuous search or optimisation over B.
- **Fold pass:** all 8 fold-level G within [1/B, B] (C1′), criterion 3 as frozen (clarified), and one-sided near-zero hours ≤ 10% of the fold's cell-metrics.
- **Rule:** at least 3 of the 4 gating folds pass, and no fold has any G outside [0.5, 2.0] (C2′).
- **Reported for each B:**
  - P(rule passes), with a 95% Wilson interval
  - P(rule passes) without C2′
  - P(all 4 folds pass)
  - per-fold pass rates
  - per-fold failure rates for C1′, criterion 3 and the near-zero cap
- **Power:** the null model's p95/p99 are multiplied by b ∈ {1.15, 1.25, 1.30, 1.50}. Each bias is applied (i) to every cell and percentile ("global"), and (ii) to one of the 8 cell-and-percentile combinations at a time ("localized"). Rejection probability is 1 − P(rule passes), reported at every B. **No power threshold is set**; the operating characteristics are reported as they are.
- **Safety bound C2′:** per-fold and family-level (any of 4 folds × 8 G) false-failure probability under the null.
- **Near-zero cap:** per-fold, any-fold, and two-or-more-folds false-failure probability under the null.
- **Criterion 3:** per-fold and any-fold failure under the null. If it shows a calibration problem, **stop and report**; don't change it.
- **Calibration target:** a perfect-model P(rule) of at least 0.80 is necessary, but not sufficient on its own to freeze a bound.
- **N2 (Azure vs bootstrap)** is report-only. It doesn't determine whether Cycle 2 proceeds.
- **Implementation:** `analysis/cycle2_operating.py` (tests: `test_criterion_audit.py`; its criterion 3 and G equal the frozen `judge_cell` and G definitions). Applied to the original R = 50 output, it reproduces section 3's rule rates exactly: 0.42 / 0.70 / 0.88 / 0.94 (C1 truth) and 0.62 / 0.86 / 0.94 / 1.00 (bootstrap), at B = 1.25 / 1.30 / 1.35 / 1.40.

---

## 7. Expanded audit results (R = 200; run 2026-10-04 from `24ec4d5`)

**Discipline record.**
- This audit and the revision it informs happened **before any Cycle 2 candidate was fitted or evaluated.**
- **No candidate results informed threshold selection;** none exist.
- **Wednesday and the raw trace were untouched.** Development caches only, through the guard. The raw file's last-access time is still 2026-09-28.
- The revised criterion is **prospective for Cycle 2.** It is **not frozen or adopted.**

Sources: `analysis/results/cycle2/criterion-audit-200.json.gz` (per-cell metrics, 200 replicates per truth, seed entropy 20261003) and `criterion-audit-200-operating.json`. Intervals are 95% Wilson.

### 7.1 Perfect-model calibration (the rule: 3 of 4 gating folds pass C1′, criterion 3 and the near-zero cap, and no fold violates C2′)

| B | P(rule), truth C1 | P(rule), truth bootstrap | P(all 4 folds), C1 / bootstrap |
|---|---|---|---|
| 1.25 | 0.440 [0.373, 0.509] | 0.400 [0.335, 0.469] | 0.075 / 0.075 |
| 1.30 | 0.650 [0.582, 0.713] | 0.635 [0.566, 0.699] | 0.200 / 0.235 |
| 1.35 | 0.815 [0.755, 0.863] | 0.795 [0.734, 0.845] | 0.390 / 0.335 |
| **1.40** | **0.900 [0.851, 0.934]** | **0.865 [0.811, 0.906]** | 0.520 / 0.450 |

**Per-fold pass rates, and the criterion that fails** (truth C1; bootstrap within about 0.15):

| B | Fri | Mon | Tue | Thu | Fold failures from C1′ | from criterion 3 | from the near-zero cap |
|---|---|---|---|---|---|---|---|
| 1.25 | 0.74 | 0.64 | 0.35 | 0.60 | 0.26–0.65 | 0.000–0.010 | 0 |
| 1.30 | 0.83 | 0.75 | 0.47 | 0.72 | 0.17–0.53 | 0.000–0.010 | 0 |
| 1.35 | 0.91 | 0.84 | 0.63 | 0.81 | 0.10–0.37 | 0.000–0.010 | 0 |
| 1.40 | 0.94 | 0.89 | 0.73 | 0.87 | 0.06–0.27 | 0.000–0.010 | 0 |

Almost all fold failures come from C1′. **Tuesday is consistently the noisiest fold**; it has the most hours above 60 rps.

**The R = 50 estimate was optimistic.** At B = 1.35 it gave 0.88 and 0.94, against 0.815 and 0.795 here. That's Monte Carlo error, plus fresh model medians. So section 4's provisional 1.35 doesn't hold up.

### 7.2 Power: P(the rule rejects a model with a known bias)

Global bias (every cell and percentile multiplied by b). Each cell shows truth C1 / truth bootstrap.

| b | B 1.25 | B 1.30 | B 1.35 | **B 1.40** |
|---|---|---|---|---|
| 1.15 | 0.70 / 0.68 | 0.41 / 0.47 | 0.23 / 0.23 | **0.13 / 0.08** |
| 1.25 | 0.97 / 0.97 | 0.84 / 0.85 | 0.65 / 0.64 | **0.46 / 0.44** |
| 1.30 | 1.00 / 1.00 | 0.96 / 0.96 | 0.84 / 0.87 | **0.71 / 0.73** |
| 1.50 | 1.00 / 1.00 | 1.00 / 1.00 | 1.00 / 1.00 | **1.00 / 1.00** |

Localized bias: one of the 8 cell-and-percentile combinations at a time. Each cell shows the range of rejection over the 8 combinations, for the C1 and bootstrap truths combined.

| b | B 1.25 | B 1.30 | B 1.35 | **B 1.40** |
|---|---|---|---|---|
| 1.15 | 0.49–0.76 | 0.25–0.51 | 0.10–0.28 | **0.05–0.17** |
| 1.25 | 0.62–0.94 | 0.33–0.74 | 0.15–0.50 | **0.08–0.31** |
| 1.30 | 0.74–1.00 | 0.45–0.88 | 0.19–0.65 | **0.10–0.44** |
| 1.50 | 0.99–1.00 | 0.91–1.00 | 0.76–1.00 | **0.63–1.00** |

At B = 1.25 and 1.30, the high rejection rates are not usable discrimination. Those bounds also reject a *perfect* model 56% and 35% of the time.

### 7.3 Safety bound C2′ (no fold-level G outside 0.5–2.0×)

- **Per fold:** 0.000 (C1 truth), and 0.000–0.005 (bootstrap truth).
- **Family-level** (any of 4 folds × 8 G = 32 comparisons): **0.000 [0, 0.019]** (C1) and **0.010 [0.003, 0.036]** (bootstrap).
- **Largest |G| per replicate:** median 1.40–1.43×, 99th percentile 1.86–1.92×, maximum 1.89× (C1) and 2.12× (bootstrap).

It **doesn't recreate the per-cell multiple-comparison problem.** The per-cell catastrophic bound fired in 92–100% of folds; C2′ fires in at most about 1% of null replicates, with an upper bound of 3.6%.

### 7.4 Near-zero cap (one-sided near-zero hours ≤ 10% of a fold's cell-metrics)

- **False failures:** 0 of 800 folds for each truth. Any-fold: 0.000 [0, 0.019].
- **One-sided fraction:** median 1.0–1.6%, 99th percentile 3.1%, maximum 3.65%.

It's calibrated, and never binds under the null.

### 7.5 Criterion 3 (unchanged)

- **Per-fold failure:** 0.000–0.010 (C1 truth) and 0.000 (bootstrap truth).
- **Any-fold failure:** 0.020 [0.008, 0.050] (C1) and 0.000 [0, 0.019] (bootstrap).

**No calibration problem**, so it stays unchanged. Its margin is thin, though: the 1st percentile of the beats-Poisson fraction is 0.83, against the 0.80 threshold. Because the rule tolerates one failing fold, that isn't a gate risk.

### 7.6 N2 (Azure vs bootstrap)

Report-only (owner decision). It doesn't determine whether Cycle 2 proceeds, and it wasn't re-analysed here.

### 7.7 Recommendation (not adopted; for the owner's decision)

**Recommended equivalence bound: B = 1.40.**

1. **It's the narrowest predeclared bound calibrated under both truth processes,** with the 95% lower bound on the perfect-model pass rate at least 0.80 (0.851 and 0.811). At B = 1.35 the lower bounds are 0.755 and 0.734, and the bootstrap point estimate (0.795) is below 0.80. This "lower bound ≥ 0.80" choice rule was written into section 4 **before** this run. It isn't satisfied merely because a point estimate crosses 0.80.
2. **It keeps useful discrimination against material bias:**
   - global 1.5× is rejected with probability 1.00;
   - global 1.30× about 72% of the time;
   - a 1.5× bias confined to a single cell-and-percentile, 63–100% of the time.

Keep with it:
- **C2′** (0.5–2.0×; family false failure ≤ 1%)
- **the 10% near-zero cap** (no null failures)
- **criterion 3, unchanged**
- **the 3-of-4 structure**

### 7.8 Measurement-resolution limitation

With one Azure realisation per hour and 24 hours per fold, the queue test **can't reliably distinguish biases below about 1.3× at p95/p99.** At B = 1.40:
- a global 1.15× bias is rejected only 8–13% of the time;
- a global 1.25× bias about 45% of the time.

Single-metric biases below 1.5× are often missed. This is a property of the data, not of the test, and no bound in the predeclared set gives both calibration and finer resolution.

Any Cycle 2 claim from this test must therefore read: **"no detectable p95/p99 bias of about 1.3× or more globally, or 1.5× or more in any single cell; smaller biases can't be excluded."** It must not read as "matches Azure".
