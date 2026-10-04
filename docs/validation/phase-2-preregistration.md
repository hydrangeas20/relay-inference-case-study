# Phase 2 validation: preregistration

- **Version:** 1, amended by [Amendment 1](#amendment-1-2026-09-28-before-thursday-validation) (resolves §10; revises §8's conditioning) and [Amendment 2](#amendment-2-2026-09-29-after-thursday-validation) (closes this validation cycle; clarifies criterion 3)
- **Date:** 2026-09-28
- **Owner:** hydrangeas20
- **Decisions:** [ADR-0005](../decisions/0005-traffic-model-revision.md)

This document fixes, before any candidate model is validated, everything the revised traffic model will be judged against. It's committed on its own, before the implementation, so the git history shows the order.

**Rule for changes.** Nothing here changes after a validation result has been seen. An amendment is a new, dated section in this file, committed *before* the run it affects. §10 lists the two items still open. No candidate validation runs until they're resolved by amendment.

The thresholds below are **engineering acceptance thresholds** chosen by the project before evaluation. They aren't established by Azure's dataset or by published literature.

---

## 1. Data

- **Source:** Azure LLM inference trace 2024, code service, one-week sample (`AzureLLMInferenceTrace_code_1week.csv`), CC-BY 4.0.
- **SHA-256:** `71de5c55cbc35f8f1ed0b6b7806b4cd1e9764b0058469725a6aac98023a1448f` (16,803,695 rows). Every script verifies this hash before reading. The file isn't committed; see `analysis/README.md` for how to reproduce.
- **Days are UTC calendar days.**

| Split | Days | Use |
|---|---|---|
| Training | Fri 05-10, Sat 05-11, Sun 05-12, Mon 05-13, Tue 05-14 | Fitting candidates, thresholds, reference artifacts |
| Validation | Thu 05-16 | Choosing between candidates; queueing test during development |
| Holdout | Wed 05-15 | Evaluated exactly once, only after explicit written authorisation |

**Holdout guard.** `analysis/common.py` drops Wednesday rows by their date prefix before any timestamp or token count is parsed. Reading Wednesday requires `allow_holdout=True`, which only the final evaluation script passes, behind a `--holdout` flag.

**Disclosure: Wednesday isn't pristine** (ADR-0005, D1). Before this preregistration, a verification audit on 2026-09-28 computed pooled statistics over all seven days, so Wednesday's hours contributed to the earlier pooled burstiness fit, the per-band values and the day-to-day spreads reported in the audit. No Wednesday-specific result was inspected. No revised model is tuned against Wednesday.

**Hours already inspected individually in the audit:** Mon 16:00, Tue 08:00, Tue 18:00, Sat 19:00 UTC. All are training days, so none is in the validation or holdout splits.

**Reference artifacts.** `traffic/reference/azure_code_hourly.csv` and `azure_code_sizes.csv` were previously derived from all seven days. They are regenerated from training days only (§8), so validation uses no data derived from Wednesday.

**Thursday facts already computed** (to size the test; no burstiness statistic): eligible hours per band 4 / 10 / 4 / 6; hourly rates 8.71–79.52 rps.

## 2. Timestamp treatment

Azure's timestamps have an unexplained 250 ms periodic structure (ADR-0005, sub-second). For every burstiness fit and every canonical validation, timestamps are **de-jittered**: each is redrawn uniformly within its 250 ms interval, using `numpy.random.default_rng(20260928)` applied to that day's sorted timestamps in order. Raw timestamps are used only for the descriptive clustered-variant comparison.

## 3. Estimator

This is `relay.traffic.stats.rate_cv2`, the single implementation used everywhere:

- **Per-hour input:** arrivals within one UTC clock hour, counted per second (3,600 counts).
- **Trend:** a centred 600 s moving average, padded at each end with the edge value.
- **Windows:** W ∈ {1, 2, 5, 10, 30, 60} s. For each, sum counts and trend over consecutive W-second windows. With Z = (count − trend)/trend, compute CV²(W) = mean(Z² − 1/trend).
- **Reporting:** the rate fluctuation at W is √max(CV², 0).

**Eligible hours** have a mean rate ≥ 3 rps. **Rate bands (fit bands):** [3, 10), [10, 30), [30, 60), [60, 120) rps, assigned by the hour's mean rate.

**Pooled band curve:** the element-wise median of CV²(W) over the band's eligible hours; its fluctuation curve is √max(median, 0). The **band rate** is the median of those hours' mean rates.

## 4. Observed range

The observed range is **[3.20, 82.83] rps**: the minimum and maximum mean rates of eligible training hours after de-jittering (119 hours). Inside this range, burstiness comes from the fitted rate relationship (AZURE-DERIVED). Outside it, burstiness comes from a pre-declared scenario (§5.3), whose values are labelled PROJECTED where they're extrapolated.

Training band sizes and rates: 33 hours at a median of 7.66 rps; 54 at 15.17; 18 at 48.54; 14 at 70.75.

## 5. Candidate models

Both candidates are fitted on training days only, and use the same generator structure. The expected rate λ(t) is the envelope × scale, before modulation. The arrival rate is λ(t)·m(t), where m(t) = exp(s_t·X_t − s_t²/2), s_t² = ln(1 + σ(λ(t))²), and X is a unit-variance Ornstein–Uhlenbeck process updated per 0.1 s bin as X_{k+1} = a_k X_k + √(1 − a_k²) ε, with a_k = exp(−0.1/τ(λ(t_k))). Arrivals within a 0.1 s bin are placed uniformly.

### 5.1 C1: power-law σ, one shared correlation time (baseline)
1. Compute the four pooled band curves (§3).
2. Fit a shared τ with a separate σ_b per band, in log space (`fit_shared_tau`).
3. Fit σ(λ) = a·λ^b by least squares on (band rate, σ_b), weighted by each band's number of hours (`fit_power_law`).
4. τ(λ) is the shared τ at every rate.

### 5.2 C2: power-law σ, banded correlation time
1. Fit each pooled band curve on its own for (σ_b, τ_b) (`fit_sigma_tau`).
2. Fit σ(λ) = a·λ^b on (band rate, σ_b), weighted by hours.
3. τ(λ) interpolates log τ_b linearly in log λ between band rates, and holds the end values beyond the outermost band rates.

### 5.3 Outside the observed range
Every trace whose expected rate leaves [3.20, 82.83] rps names a scenario:

| Scenario | σ outside the range | τ outside the range | Role |
|---|---|---|---|
| `edge` | σ at the nearest range boundary | τ at that boundary | Canonical default |
| `poisson` | 0 | n/a | Low-burst sensitivity |
| `trend` | a·λ^b extrapolated (PROJECTED) | τ at the nearest boundary | Extrapolated sensitivity |

Traces record their scenario and the fraction of time spent out of range. Generating an out-of-range trace without naming a scenario is an error. `trend` values are never presented as empirical estimates.

## 6. Out-of-sample criterion

### 6.1 Tolerance
For each tolerance band: take the daily pooled curves of the training days that have at least 3 eligible hours in the band, and compute their standard deviation (ddof = 1) at each window. The band's tolerance is **2 × the maximum of that standard deviation over the six windows**.

| Band | Training days used | Tolerance |
|---|---|---|
| 3–10 rps | Fri, Sat, Sun, Mon, Tue | **0.0985** |
| 10–30 rps | Fri, Sat, Sun, Mon, Tue | **0.0321** |
| 30–60 rps | Fri, Mon, Tue | **0.0146** |
| 60–120 rps | *open item O2 (§10)* | — |

### 6.2 Thursday check (per band present on Thursday)
- **Observed:** Thursday's pooled band curve.
- **Predicted:** for each eligible Thursday hour, the candidate's CV²_h(W) = σ(λ_h)²·ou_shape(W, τ(λ_h)), where λ_h is the hour's mean rate. Take the element-wise median across the band's hours, then the square root.
- **Pass for the band:** |predicted − observed| ≤ tolerance at all six windows. *A second clause is open item O1 (§10).*
- **The candidate passes Thursday** if every band present on Thursday passes.

### 6.3 Rate-band holdouts (training days only)
- For each fit band b: refit the candidate on the other three bands' training hours, predict band b's training hours as in §6.2, and compare with band b's pooled training curve, using band b's tolerance.
- The **interpolation holdouts** (10–30 and 30–60) count toward generalization: a candidate that fails either one fails generalization.
- The **extrapolation holdouts** (3–10 and 60–120) are reported only. A failure there is evidence against the `trend` scenario, not grounds to reject the candidate (the model isn't used outside the observed range).

## 7. Queueing test

**Reference hours.** All eligible Thursday hours: 24 in development. The holdout run later uses all eligible Wednesday hours.

**Reference arrivals.** De-jittered Azure timestamps (§2) for the hour.

**Trend.** The 600 s moving average of the reference's per-second counts (§3), held constant within each second.

**Arrivals compared** (each hour):
- **Model:** the candidate's arrivals, with expected rate equal to the trend; σ and τ evaluated at the trend (the `edge` scenario outside the range); 20 seeds.
- **Poisson control:** the same trend with σ = 0; 20 seeds.
- Seed for hour h and replicate r: 10,000·h + r, r = 1…20. The Poisson control uses 500,000 + 10,000·h + r.

**Queue.** c identical servers, first come first served, fixed service time s, starting empty at the start of the hour.

**Cells.** 24 hours × s ∈ {0.2, 1.0} s × target utilisation ρ ∈ {0.6, 0.8} = **96 cells**, with c = ceil(λ_ref · s / ρ), where λ_ref is the reference's mean rate for the hour. The actual utilisation is recorded.

**Metrics per run:**
- p50, p95 and p99 of per-request waiting time
- fraction of requests that wait more than zero
- peak number waiting
- worst 60 s average wait, over 60 s windows of arrival time

The model's (or control's) value for a cell is the median of its 20 runs.

**Operational definitions** (fixed before any run):
- For metric m ∈ {p95, p99}: A = Azure's value, M = the model's median, P = the control's median, thr = 0.01·s.
- **Near-zero rule:** if A < thr and M < thr, the model agrees on m. If exactly one of A and M is below thr, the model fails on m. The same rule applies to P for the control.
- Otherwise R_model = M/A and R_poisson = P/A.

**Criteria** (all three must hold):
1. **Band:** a cell passes if, for both p95 and p99, the model agrees (near-zero) or 0.67 ≤ R_model ≤ 1.5. At least **80%** of cells must pass.
2. **Bounds:** no cell may have R_model < 0.5 or > 2.0 for p95 or p99. A near-zero one-sided failure where A = 0 counts as out of bounds; where A > 0, the actual ratio is used.
3. **Beats Poisson:** a cell counts if, for both p95 and p99, the model's error |log R| is strictly smaller than the control's, where near-zero agreement counts as error 0 and near-zero failure as infinite error. Cells where both model and control agree by the near-zero rule on both metrics are **ties**. Ties are excluded from this criterion's denominator and reported. The model must beat Poisson in at least **80%** of non-tie cells.

Fraction waiting, peak queue length and worst-60-second wait are **reported diagnostics**, not pass/fail criteria.

## 8. Prompt-size fidelity

**Evaluation trace:** `relay-trace window --start 15:00 --minutes 60 --peak-rps 8 --seed 20260928`, canonical scenario, generated from training-derived reference artifacts.

**Template minimum:** the smallest prompt Relay's completion template can produce, i.e. the template with an empty code prefix and no context files, plus the 100-character minimum prefix, for the request's own IDs and path. Targets below it are **structurally below the template minimum**: kept as generated, flagged, never resampled (ADR-0005, D6).

**Built size:** measured by the gateway (`X-Relay-Prompt-Chars`), running in-process against a fake inference server. It's converted to tokens at 3.5 characters per token, a temporary stand-in until Phase 3's tokenizer.

**Pass/fail** (representable targets only): a two-sample Kolmogorov–Smirnov test between built sizes (in tokens) of representable completions and the training-derived Azure size sample restricted to values at or above the minimum representable size. It passes if D < 1.358·√((n+m)/(n·m)), the 5% critical value.

**Reported separately:** the fraction of all targets below the template minimum; their target sizes, built sizes and inflation (built ÷ target); and the fraction of all completions whose built size differs from the generator's expected size.

## 9. Sensitivity (descriptive, no pass/fail)

For a canonical GPU window (the §8 spec) and a day trace (`relay-trace day --peak-rps 20 --seed 20260928`), report:
- the fraction of time out of the observed range
- σ over time under `edge`, `poisson` and `trend`
- queue metrics (s ∈ {0.2, 1.0}, ρ = 0.8, 20 seeds) for the day trace's out-of-range hours under each scenario

The clustered variant is compared with **raw** Thursday timestamps descriptively: gaps under 1 ms, mean cluster size and 250 ms phase uniformity. Raw Azure isn't an acceptance reference.

## 10. Open items (must be resolved by amendment before any candidate validation)

*Both resolved by [Amendment 1](#amendment-1-2026-09-28-before-thursday-validation).*

**O1: The sign-consistency clause** ("errors don't all share one sign across the six windows") **rejects real data.** In leave-one-day-out comparisons on training days (one day's pooled band curve against the median of the other days'), 12 of 13 comparisons had all six errors in the same direction. Day-to-day variation shifts the whole curve, so an ideal model of the population would fail this clause about 92% of the time. The magnitude clause passed 13 of 13 of the same comparisons.

**O2: The 60–120 rps tolerance can't be estimated as specified.** Only Mon and Tue have ≥ 3 eligible hours in the band. The two-day standard deviation gives a tolerance of 0.0035, which can't be checked for false failures. Options evaluated on training data:

| Option | Tolerance | Days | Leave-one-day-out null |
|---|---|---|---|
| (a) Merge 30–60 and 60–120 for tolerance: one 30–120 band used for both Thursday checks | 0.0102 | Fri, Mon, Tue | 3/3 within |
| (b) Two-day estimate as specified | 0.0035 | Mon, Tue | Not checkable |
| (c) Use the 30–60 tolerance for 60–120 | 0.0146 | Fri, Mon, Tue (borrowed) | n/a |

## 11. Selection rule (Thursday)

- If both candidates pass all Thursday criteria (§6.2, §6.3 interpolation holdouts, §7), **C1 is selected** (fewer parameters).
- If exactly one passes, it's selected.
- If neither passes, the candidate with the larger fraction of queueing cells meeting criterion 1 is recorded as the provisional choice, and the result is reported as "no candidate passed on Thursday." Nothing is tuned against Thursday after this point.

## 12. After Thursday

Results are reported in full and work stops. Wednesday runs **exactly once, only after explicit written authorisation**, with the selected candidate and every procedure exactly as written here. A failure is recorded, and it limits Phase 2's claims. There's no tuning, threshold change, model change or rerun against Wednesday (ADR-0005, D9). Any later revision is a new validation cycle, and must state that this Azure week no longer contains an unused holdout.

**Merge gate:** Phase 2 stays unmerged until the preregistered Wednesday evaluation has been run exactly once and its result, pass or fail, has been documented and reviewed. *(Superseded for Cycle 1 by Amendment 2 and the [Cycle 1 closure](#cycle-1-closure-2026-09-29) below; kept here as originally written.)*

---

## Amendment 1 (2026-09-28, before Thursday validation)

- **Decided by:** hydrangeas20, 2026-09-28
- **Committed:** before any Thursday candidate validation, and before the amended prompt-fidelity run. No Thursday burstiness or queueing statistic, and no Wednesday data of any kind, had been computed when this was written.

This amendment resolves O1 and O2 (§10) and corrects the conditioning in the prompt-fidelity test (§8). Where it conflicts with the sections above, it takes precedence. The text above is otherwise unchanged.

### A1.1 O1: the sign clause becomes a reported diagnostic

- **Pass/fail (§6.2, §6.3):** a band passes if |predicted − observed| ≤ tolerance at all six windows. That's the only clause. The rule "errors don't all share one sign" is removed from pass/fail.
- **Reported diagnostic:** for every band check (Thursday bands, band holdouts, and later the Wednesday bands), the sign of the error at each of the six windows and whether all six share one sign are reported. They don't affect any verdict.
- **Not replaced by a recalibrated sign threshold.** Thirteen leave-one-day-out comparisons are too few independent comparisons to calibrate one.
- **Reason:** in the training leave-one-day-out comparisons (§10, O1), 12 of 13 real day-versus-other-days comparisons had all six errors sharing a sign. Day-level shifts move the whole curve, so the clause doesn't separate model failure from ordinary day-to-day variation, and it would reject realistic data about 92% of the time.

### A1.2 O2: one tolerance from the merged 30–120 rps population, two separate evaluation bands

- **Tolerance:** the §6.1 method applied to the merged 30–120 rps training population (days with ≥ 3 eligible hours in 30–120: Fri, Mon, Tue): **0.0102**.
- **Evaluation stays separate.** Thursday, and later Wednesday, check and report two bands:
  - **30–60 rps:** error against 0.0102
  - **60–120 rps:** error against 0.0102

  The two bands' curves are not pooled for evaluation, so performance in one band can't hide failure in the other.
- **This supersedes 0.0146 for 30–60.** It applies to the Thursday and Wednesday band checks (§6.2) and to the 30–60 and 60–120 rate-band holdouts (§6.3). The 3–10 and 10–30 tolerances are unchanged.

| Band | Tolerance |
|---|---|
| 3–10 rps | 0.0985 |
| 10–30 rps | 0.0321 |
| 30–60 rps | **0.0102** (was 0.0146) |
| 60–120 rps | **0.0102** |

- **Reason:**
  - The original 60–120 estimate uses only Mon and Tue, so it can't get the same leave-one-day-out training check as the other bands.
  - Borrowing the 30–60 tolerance has no direct statistical basis.
  - The merged 30–120 estimate uses the available higher-rate training population across three days, and passed its training check in 3 of 3 comparisons.
- **Disclosure:** before this decision, the owner had been told C1's in-sample training error in the 60–120 band: **0.0062**. That value passes options (a) and (c) and fails (b). C1's in-sample 30–60 error (0.0069) was also known, and passes at 0.0102. Option (a) was chosen on the tolerance-estimation method, not on C1's pass/fail outcome. Both numbers are in-sample (training days). No Thursday or Wednesday value was known.

### A1.3 Prompt fidelity: representability is judged per request

**Correction.** The first fidelity run conditioned both samples on one global cutoff, T = 636 characters: the largest per-request template minimum in the trace. That cutoff wasn't preregistered. §8's wording ("restricted to values at or above the minimum representable size") didn't fix it, and it was chosen when the test first ran. It also excluded 115 targets that were representable for their own request.

**Disclosure.** The first result was observed before this correction: KS D = 0.00598 against a 5% critical value of 0.01309 (PASS), n = 25,257 built and 18,747 Azure (`analysis/results/validation-prompt-fidelity.json`). That file is kept unchanged. The amended result is written to a separate file, and both are reported.

**Amended procedure** (same evaluation trace, same gateway measurement, same 3.5 characters per token):

1. **Per-request minimum.** For each completion i, m_i = the length of Relay's completion prompt for that request's own ID, repository, path and language, with an empty code prefix and no context files, plus the 100-character minimum prefix. The generator drops context files that don't fit, so this is the smallest prompt that is structurally possible for request i.
2. **Inclusion.** Request i is in the conditional fidelity evaluation if its target in characters, round(target_tokens × 3.5), is ≥ m_i.
3. **Structurally unrepresentable targets** (target < m_i) are kept as generated, flagged, and excluded from pass/fail. The report gives their count and fraction, target sizes, built sizes and inflation (built ÷ target). No global cutoff is used for inclusion.
4. **Reference distribution (matched mixture).** The null distribution for an included request's size is the Azure size sample conditioned on ≥ m_i. The reference CDF is the average of those conditional CDFs over the n included requests: F_ref(x) = (1/n) Σ_i F_Azure(x | round(X × 3.5) ≥ m_i), computed from the training-derived 20,000-row Azure sample.
5. **Statistic and threshold.** D = sup_x |F_built(x) − F_ref(x)|, evaluated at every built and Azure value. The test passes if D < 1.358·√((n+m)/(n·m)), with n = included requests and m = Azure sample values ≥ min_i m_i. Using all m of those values makes the threshold slightly stricter than the effective reference sample size would.
6. **Also reported:** built-versus-expected mismatches; the ratio of built size to target size for included requests (1st, 50th and 99th percentiles, and the count more than 0.5% short); and gateway rejections, which are excluded as before.

**Known imperfection.** m_i depends on the file the generator picks, and the pick depends on the target, which favours files long enough for it. Per-request minimums in the first run ranged from 561 to 636 characters (160–182 tokens), so the dependence can affect only that narrow range.

### A1.4 Other findings (no change to procedure)

- The gateway's 4,096 `max_tokens` limit is unchanged in Phase 2. Rejected Azure-sized requests are reported as a limitation and product constraint.
- The estimator's slight upward bias at low rates and τ's dependence on the detrending window are documented as limitations (ADR-0004). They don't change the estimator.
- The possible retry or duplicate signal at low rates (identical context sizes among sub-millisecond pairs) is an exploratory finding. It doesn't change the canonical sub-second model.

### A1.5 Unchanged

Everything else stays as written: the data split and holdout guard, the estimator, the candidates, the queueing test and its thresholds, the selection rule (§11) and the holdout procedure and merge gate (§12). Wednesday is still not authorised.

---

## Amendment 2 (2026-09-29, after Thursday validation)

- **Decided by:** hydrangeas20, 2026-09-29
- **Committed:** after the Thursday results (`4a0cbc3`) and before any further diagnostic analysis. No Wednesday data of any kind has been accessed.

Unlike Amendment 1, this amendment is written **after** Thursday's results were observed. It changes no threshold, candidate or verdict. It records the outcome, closes this validation cycle, and clarifies one rule for any future cycle.

### A2.1 Outcome of Thursday validation

1. **Neither C1 nor C2 passed Thursday validation** (§6.2, §6.3, §7 as amended by Amendment 1). Results: `analysis/results/validation-validation.json`.

   | | C1 | C2 |
   |---|---|---|
   | Thursday band checks (§6.2) | Fail (30–60 rps: 0.0113 vs 0.0102) | Pass |
   | Interpolation holdouts (§6.3) | Pass | Pass |
   | Queueing criterion 1 (≥ 80% of cells in band) | Fail (44/96) | Fail (47/96) |
   | Queueing criterion 2 (no cell out of bounds) | Fail (25 cells) | Fail (27 cells) |
   | Queueing criterion 3 (beats Poisson in ≥ 80%), as run | Fail (58/87) | Fail (58/87) |

2. **C2 is a provisional fallback only.** §11 names it because it had the larger criterion-1 fraction (0.490 vs 0.458). It is **not validated** and must not become the canonical or default model.
3. **`traffic/relay.toml` stays unchanged** (`candidate = "C1"`, marked provisional) for now. Neither candidate is validated. The default is a placeholder, not a validated choice.
4. **Wednesday won't be run.** No candidate passed the Thursday gate, so there is no validated candidate to evaluate. The holdout stays untouched and remains available to a future validation cycle.

### A2.2 Gate from Thursday to Wednesday (prospective)

This rule applies to this and every future validation cycle on this dataset:

- **At least one candidate passes Thursday:** the passing candidates are eligible for selection under §11, and the selected candidate gets one Wednesday evaluation (§12).
- **No candidate passes Thursday:** the validation cycle stops. Wednesday stays untouched. §11's provisional choice is recorded for information only, and gives no candidate a right to a Wednesday evaluation.

`analysis/validate.py --holdout` enforces this: it refuses to run unless the Thursday results file shows a non-provisional selection.

### A2.3 Criterion 3 clarified (near-zero metrics)

**The ambiguity.** §7 criterion 3 says a cell counts if "for both p95 and p99, the model's error |log R| is strictly smaller than the control's, where near-zero agreement counts as error 0." Read literally, when Azure and the candidate are both near zero on one metric, the candidate's error there is 0. If the control is also near zero on that metric, its error is 0 too. Since 0 isn't strictly smaller than 0, the cell can't count, even when the candidate is closer on the other metric.

**Clarified rule:**

- A metric (p95 or p99) where Azure and the candidate are both in the near-zero-agreement state (§7) is **non-informative** for criterion 3.
- The remaining informative metric decides the comparison: the candidate beats the control if its |log R| is strictly smaller on every informative metric, using the §7 errors (near-zero failure = infinite).
- If both metrics are non-informative, the cell is non-informative (tied) and is excluded from criterion 3's denominator.

Criteria 1 and 2 and every threshold are unchanged.

**Disclosure.** This ambiguity was found **after** the Thursday results were observed, by an independent re-implementation of §7 from the text. The clarification is adopted because the literal reading penalises a candidate for agreeing with Azure. It is not adopted to change an outcome.

**Both results are preserved:**

| Criterion 3 on Thursday | C1 | C2 |
|---|---|---|
| Original literal interpretation (as run, stored in `validation-validation.json`) | 58/87 (66.7%), fail | 58/87 (66.7%), fail |
| Clarified interpretation (recomputed from the stored cell values) | **73/87 (83.9%), pass** | **73/87 (83.9%), pass** |

Under the clarified rule, 15 cells change from "doesn't beat Poisson" to "beats Poisson", all at 60% utilisation. The same 9 cells are excluded under both readings. Recomputation: `analysis/results/validation-validation-criterion3-clarified.json`. The original results file is unchanged.

**The overall Thursday verdict doesn't change.** Both candidates still fail queueing criteria 1 and 2, and therefore the queueing test and Thursday validation.

### A2.4 What happens next

- Further analysis of this failure is **diagnostic**: it uses training days and Thursday only, and it doesn't tune C1 or C2, create a new candidate, change thresholds or search parameters.
- A revised model is a **new validation cycle** with its own preregistration. Thursday has now been used to reveal this failure, so a new cycle has to either justify reusing Thursday as its validation split or define a new one. It must also state which data informed the revision.
- Wednesday stays untouched until a future cycle's candidate passes that cycle's pre-Wednesday gate.

---

## Cycle 1 closure (2026-09-29)

- **Decided by:** hydrangeas20, 2026-09-29
- **Nature:** a record of the outcome and the owner's decisions after Amendment 2. It changes no threshold, candidate, parameter or result.

**Cycle 1 is closed as a FAILED VALIDATION cycle.**

- Training fit: **completed** (C1 and C2, Fri–Tue).
- Thursday validation: **completed**.
- Prompt fidelity: **passed** (representable targets, per-request matched-mixture KS).
- Queue-tail acceptance: **failed** (both candidates fail criteria 1 and 2).
- Candidates validated: **none**. C2 was the selection rule's fallback only.
- Wednesday: **not accessed**. No Wednesday timestamp or statistic has been computed.
- Burstiness model: **UNVALIDATED**.
- Phase 2 infrastructure may merge. **No traffic-model validation claim may be made.**

**Merge gate.** The §12 gate ("stays unmerged until the preregistered Wednesday evaluation has been run exactly once…") is **superseded for Cycle 1 by Amendment 2**, which stops the cycle without a Wednesday run. As written, the gate can't be met by a cycle that never reaches Wednesday, so it no longer governs merging Phase 2. It stays in §12 as the historical record. The replacement condition: Phase 2 may merge as infrastructure (generator, trace format, identity, prompt sizing, measurement and reconciliation, and the analysis and validation tooling). Every document and result must state that the burstiness model is unvalidated. No claim that synthetic traffic reproduces Azure's queueing behaviour may be made.

**Next cycle.** A revised model is Cycle 2, with its own preregistration. The research direction and the proposed protocol are recorded in the [queueing diagnosis](phase-2-queueing-diagnosis.md), sections E–G. Wednesday is untouched and remains the final lockbox for Cycle 2.

---

## Methodological note on criteria 1 and 2 (2026-10-03)

- **Added by:** hydrangeas20's instruction, 2026-10-03
- **Nature:** a dated note. Every Cycle 1 result, verdict and amendment above is preserved unchanged. **Cycle 1 remains a failed validation cycle; it isn't relabelled as passing.**

**What was found later.** A candidate-independent audit during Cycle 2, carried out before any Cycle 2 candidate was fitted ([criterion audit](phase-2-cycle-2-criterion-audit.md)), found that queue criteria 1 and 2 (§7) were **not calibrated to the finite-sample variability of hourly p95/p99 estimates.**
- When the "model" is the true process itself (a perfect model), a single hour's p99 varies by roughly 0.5–1.8× around the truth at 80% utilisation.
- So a perfect model meets criterion 1 (≥ 80% of cells in 0.67–1.5×) and criterion 2 (no cell outside 0.5–2.0×) in essentially no fold: 0 of 50 replicates, for two different truth processes.
- Criterion 3 was not affected.

**Consequence for interpretation.** C1's and C2's Thursday failures on criteria 1 and 2 **should not, on their own, be read as evidence of model misspecification.** A correctly specified model would also have failed those criteria with high probability.

**What is unchanged:**
- The **aggregate mismatch.** Across hours, C1's median p99 was about 1.3× Azure's on training days and 1.2–1.5× by cell on Thursday. The null's median ratio is about 1.00.
- The **surrogate diagnostic findings** (the per-second count distribution and the 5–30 s time structure are each sufficient to raise queue tails).

These rest on aggregate comparisons and controlled experiments, not on criteria 1 and 2, and remain the evidence that the Cycle 1 candidates misrepresent queue tails ([queueing diagnosis](phase-2-queueing-diagnosis.md)).
