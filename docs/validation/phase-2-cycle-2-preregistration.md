# Phase 2, Cycle 2: preregistration (pre-candidate skeleton)

- **Version:** 0 (pre-candidate skeleton), 2026-10-02, amended by [Amendment 1](#amendment-1-2026-10-05-final-queue-validation-rule-prospective) (2026-10-05: final queue-validation rule, frozen)
- **Owner:** hydrangeas20. Design decisions Q1–Q9 approved 2026-10-02.
- **Frozen values in code:** `analysis/cycle2_config.py`
- **Statistics implementation:** `relay.traffic.higher_order` (S2–S5) and `relay.traffic.stats` (S1)

**Commit order.** This skeleton is committed **before** any Cycle 2 target value is computed, before the criterion audit runs, and before any candidate is fitted. It fixes:
- the definitions
- the loss
- the model classes and the variant cap
- the audit procedure and its decision thresholds
- the validation structure
- selection, falsification and the Wednesday gate

Numerical tolerances from development data are computed and frozen afterwards, in a dated amendment. Changes follow the Cycle 1 rule: a dated amendment, committed before the run it affects. Nothing changes after the result it would affect has been seen.

**No candidate (D, A, B) is fitted until the owner explicitly authorises it.**

---

## 1. Carried forward from Cycle 1 (fixed history)

Cycle 1 is closed as a failed validation cycle (Cycle 1 preregistration, Amendment 2 and the Cycle 1 closure). Its results aren't revisited.

**Correction to a restatement (Q1).** In the 2026-10-02 design request, one finding was restated with its direction reversed ("training traffic showed greater 10 s skew/kurtosis and stronger high-rate persistence"). The Cycle 1 record is correct and unchanged ([diagnosis memo](phase-2-queueing-diagnosis.md), section A). It was **synthetic C1, relative to Azure's training traffic,** that showed this. On training days, medians over 119 hours:

| Statistic | C1 | Azure |
|---|---|---|
| 10 s skewness | 0.42 | 0.29 |
| 10 s excess kurtosis | 0.32 | 0.10 |
| Top-5% persistence at 5 s | 0.20 | 0.14 |
| Bottom-5% persistence at 5 s | 0.15 | 0.14 |

So Cycle 2 needs a marginal *less* right-tailed than C1's log-normal link.

## 2. Data

- **Development data:** Fri 05-10, Sat 05-11, Sun 05-12, Mon 05-13, Tue 05-14 and Thu 05-16. Thursday informed the Cycle 1 diagnosis, so it is **development data**, not untouched validation data.
- **Final lockbox:** Wednesday 05-15. It isn't accessed, parsed, summarised, tested or used for tuning during Cycle 2 development.
- **Cache-only, fail-closed (Q2).** Cycle 2 code reads only `training.npz` and `validation.npz`, through `analysis/cycle2_data.py`, after `enter_cycle2_mode()`. Their SHA-256 hashes and day sets are recorded in `analysis/cycle2_cache_manifest.json`:
  - `training.npz` `1f0e15da…b92362`
  - `validation.npz` `47ea7ddf…a4fde7`

  The raw file isn't opened, hashed, scanned or used to rebuild anything. An audit hook blocks any open of it in the Cycle 2 process. A missing or altered cache is an error, never a fallback.
- **Timestamps** are de-jittered within 250 ms, as in Cycle 1 (seed 20260928).
- **Eligible hours** have a mean rate ≥ 3 rps. Rate bands are [3, 10), [10, 30), [30, 60) and [60, 120) rps.

| Eligible hours | 3–10 | 10–30 | 30–60 | 60–120 |
|---|---|---|---|---|
| Fri | 5 | 9 | 9 | 1 |
| Sat | 8 | 15 | 0 | 0 |
| Sun | 10 | 14 | 0 | 0 |
| Mon | 5 | 8 | 5 | 6 |
| Tue | 5 | 8 | 4 | 7 |
| Thu | 4 | 10 | 4 | 6 |

## 3. Model classes and variant cap

The generator is shared by all classes. For each 0.1 s bin k, Nₖ ~ Poisson(λₖ·Mₖ·Δ), with λₖ the envelope × scale and E[M] = 1. Classes differ only in the modulation M. In every class, σ(λ) = a·λ^b inside the observed rate range.

| Variant | Class | Modulation | Effective parameters |
|---|---|---|---|
| D1 | Salvage | Cycle 1 structure: M = exp(sX − s²/2), with X one unit-variance OU (τ) and s² = ln(1 + σ²) | 3: a, b, τ |
| A1 | **Primary** | Y = √w·F + √(1−w)·S, with F and S independent unit-variance OU processes (τ_f < τ_s, updated exactly per bin). M = Q_{σ,ξ}(Φ(Y)), where Q is a mean-1 standardised sinh-arcsinh quantile function with standard deviation σ(λ), skewness parameter ξ, and tail weight fixed at Gaussian. Clipped at 0.02 | 6: a, b, ξ, w, τ_f, τ_s |
| A2 | Primary | As A1, with ξ(λ) = c·λ^d | 7 |
| B2 | Alternative | Markov-modulated Poisson process, 2-state birth–death chain, levels mᵢ with Σπᵢmᵢ = 1, scaled by mᵢ(λ) = 1 + (σ(λ)/σ_ref)(mᵢ − 1) | 5 |
| B3 | Alternative | As B2 with 3 states | 8 |
| C | **Comparator only** | Within-band stationary block bootstrap of Azure's relative-rate paths from other development days (as defined in section 7) | n/a |

- **Variant cap:** at most the five variants above get internal validation. Any other variant needs a dated amendment before it's run.
- **Comparator C** is never eligible for Wednesday or for canonical Relay generation (Q6).

**Out-of-range scenarios (Q8).** Outside the observed rate range, only σ(λ) may extrapolate, under the frozen `trend` scenario. Marginal-shape and temporal-structure parameters (ξ, w, τ_f, τ_s and the state structure) are held at their boundary values. Such traffic is labelled PROJECTED or extrapolated, never validated.

## 4. Statistics and calibration

**Statistics.** One implementation is used for data and models alike. All are per eligible hour, pooled per rate band as the element-wise median across the band's hours:

| | Definition | Role |
|---|---|---|
| S1 | √max(CV²(W), 0) for W ∈ {1, 2, 5, 10, 30, 60} s (Cycle 1 estimator, unchanged) | Calibration target |
| S2 | Autocorrelation of the 1 s relative rate z = n/e − 1 at lags 1, 2, 5, 10, 20, 30 and 60 s | Calibration target |
| S3 | For W = 10 s (and W = 5 s, reported only): skewness, excess kurtosis, and standardised quantiles at 0.01, 0.05, 0.95, 0.99 and 0.999 of r_W = Σn/Σe − 1 | Calibration target (W = 10 s) |
| S4 | Top-5% and bottom-5% persistence of the 3 s-smoothed z at lags 1, 2, 5, 10 and 20 s | Calibration target |
| S5 | Exceedance of the 5 s-smoothed z above +25% and +40% (fraction, runs per hour, mean run, mean area); per-second fluid-backlog p99 for each queue cell | **Diagnostic only (Q7).** Never in the loss or in selection |

**Calibration loss.** L(θ) = Σ over bands Σ over S1–S4 target statistics of ((ŝ_sim(θ) − s_obs) / sd_days)².
- s_obs is the band-pooled development value.
- ŝ_sim is the band-pooled value from simulating each of the band's development hours on its own trend, with 3 seeds per hour drawn from the calibration seed range. The same common random numbers are used for every θ.
- sd_days is the standard deviation (ddof = 1) across development days of that day's band-pooled value, over days with ≥ 3 eligible hours in the band. It is floored at 0.25 × the median of that statistic's sd_days across bands.

**Optimiser.** 8 preregistered starting points, then Nelder–Mead, with at most 300 loss evaluations per fit. B's state structure is initialised by EM on per-second counts, with the trend as an offset, before the loss refinement.

**Queue metrics never enter the loss.**

## 5. Tolerances (method frozen here; values in a later amendment)

The Cycle 1 §6.1 method is reapplied per band to the six development days (Q5). A band's tolerance is 2 × the maximum, over windows, of the day-to-day standard deviation, using days with ≥ 3 eligible hours in that band. A band qualifies only with ≥ 3 such days.
- From the table in section 2: 3–10 and 10–30 have 6 days, 30–60 has 4 (Fri, Mon, Tue, Thu), and 60–120 has 3 (Mon, Tue, Thu). So all four bands qualify.
- The Cycle 1 merged 30–120 workaround is retired for Cycle 2 only. The Cycle 1 method and results are preserved as history.

The same method gives tolerances for S2–S4, which are reported as diagnostics in internal validation.

## 6. Internal validation (development data only)

- **Leave-one-day-out.** For each development day d:
  - fit the candidate on the other five days;
  - evaluate on day d: the queue test, plus S1–S4 band comparisons, which are reported;
  - the queue test is unchanged from Cycle 1. Cells are 24 hours × s ∈ {0.2, 1.0} × ρ ∈ {0.6, 0.8}, with c = ⌈λ_ref·s/ρ⌉, 20 seeds from the validation range, a Poisson control and the near-zero rule. The criteria:
    - band 0.67–1.5 in ≥ 80% of cells
    - no cell outside 0.5–2.0
    - beats Poisson in ≥ 80% of informative cells, under the clarified criterion 3 (Cycle 1 Amendment 2, A2.3)
- **Gating folds:** Fri, Mon, Tue, Thu. Sat and Sun are reported only; they have no hours above 30 rps.
- *Superseded by [Amendment 1](#amendment-1-2026-10-05-final-queue-validation-rule-prospective): the queue criteria below are replaced by the frozen aggregated rule. The text is kept as written.*
- **Internal pass rule (Q3, provisional; subject to the audit in section 7):**
  - at least **3 of the 4** gating folds each pass all three queue criteria; **and**
  - **no** gating fold contains a catastrophic cell: a p95 or p99 ratio below **0.25** or above **4.0**, or a one-sided near-zero failure where Azure's value is 0.
  - **Note for the owner:** the catastrophic bound (0.25–4.0, the 0.5–2.0 bound widened by a factor of 2 in log space) is proposed here so that it's fixed before the audit. The audit measures its false-alarm rate.
- **This is INTERNAL validation.** Every development day informed the Cycle 1 diagnosis, and this cycle's choice of model class. It isn't fresh out-of-sample validation and is never described as such.
- **Rate-band holdouts** (10–30 and 30–60, as in Cycle 1) are reported.

## 7. Candidate-independent criterion audit (runs before any candidate is fitted)

**Purpose.** To check that the provisional pass rule in section 6 is statistically coherent: that a model *equal to the truth* would pass it reliably, and whether Azure's own transferable structure passes it. The audit uses no Cycle 2 candidate. Its truth stand-ins are the fixed Cycle 1 C1 process and the comparator-C bootstrap.

**Shared setup.**
- The 4 gating folds, all 24 eligible hours each, and 4 cells per hour: 96 cells per fold.
- Each hour's trend is the 600 s moving average of its de-jittered Azure per-second counts. Servers are c = ⌈λ_ref·s/ρ⌉, with λ_ref the Azure hour's mean rate.
- Per-cell verdicts use `judge_cell` with the clarified criterion 3, and per-fold verdicts use `accept`. These are exactly the Cycle 1 functions.
- The Poisson control is the median of 20 Poisson realisations on the same trend.
- Seeds come from the audit range, derived from SeedSequence(20261002) and (process, fold, hour, role, replicate).

**N1: self-consistency (perfect-model) null.** For each truth process P ∈ {Cycle 1 C1 driven by the hour's trend; bootstrap B_d defined below}:
- **Model:** the median of 20 realisations of P.
- **References:** R = 50 further independent realisations of P. Replicate r uses realisation r as the "Azure" reference for every hour of the fold.
- **Per fold:** the fraction of replicates passing each criterion, all three together, and the catastrophic bound.
- **Rule:** replicate r passes if ≥ 3 of the 4 folds pass all three criteria and no fold has a catastrophic cell. Reported as P_rule, the fraction of the 50 replicates.

**N2: Azure-vs-Azure null.**
- **Reference:** the real (de-jittered) Azure hour.
- **Model:** the median of 20 realisations of bootstrap B_d, built only from the *other five* development days.
- **Result:** one verdict per fold, and the rule verdict.

**Bootstrap B_d** (comparator C, as a null instrument only).
- **Source pool:** for a target hour of rate band b on day d, the eligible band-b hours on development days other than d. Where available, keep only sources whose mean rate is at least the target's.
- **Resampling:** a stationary (Politis–Romano) bootstrap over source seconds, with mean block 120 s. Each block starts at a uniform second of a uniformly chosen source hour, and wraps within that hour.
- **Rescaling to the target trend:**
  - If p = e_tgt(t)/e_src(u) ≤ 1: n_t ~ Binomial(n_src(u), p). This thins the source exactly, so its relative modulation is kept and the counting noise is right for the target rate.
  - If p > 1: n_t = n_src(u) + Poisson((p − 1)·n_src(u)). This is an approximation; the fraction of affected seconds is reported.
- **Within-second placement:** uniform. Cycle 1 surrogate E0 showed it has no effect on queue p99.

**Decision rules, fixed before the audit runs:**

| Outcome | Meaning | Action |
|---|---|---|
| N1 P_rule ≥ 0.80 for **both** truth processes, catastrophic false-alarm rate ≤ 0.05 per fold, **and** N2 passes the rule | The rule is coherent and attainable | Proceed: compute the tolerances (section 5) after authorisation |
| N1 P_rule < 0.80 for either truth process, or catastrophic false alarms > 0.05 in any fold | Poorly calibrated: even a perfect model fails too often | **Stop.** Report, and propose a prospective revision justified only by N1 (Q4). No candidate is fitted until it's reviewed and committed |
| N1 passes but N2 fails | The criteria may demand more than Azure's day-to-day structure allows | **Stop and report** (Q4) |

The audit reports per-criterion pass rates, so that any revision targets the criterion responsible. The audit result can't be used to choose between candidates, because none exists yet.

## 8. Selection (Q6)

- **Who's eligible:** candidates passing the internal rule under identical frozen criteria.
- **Default:** the one with the **fewest effective parameters** (section 3).
- **Exception:** a more complex candidate is chosen only if it shows a **materially meaningful validation advantage**, defined as passing all three criteria in **more gating folds** than the simpler one (for example 4 of 4 against 3 of 4). The highest criterion-1 fraction is **not** a selection criterion.
- **Comparator C** is never eligible.

## 9. Falsification rules (a class is rejected if any one holds)

**All classes:**
- **(F0)** It fails the internal pass rule.
- **(F1)** It fits its in-sample targets within 2 × sd_days but still fails the queue test. That's "a descriptive match isn't enough", recorded as such.

**A:**
- **(FA1)** The fit collapses to Cycle 1's structure: w at 0 or 1, τ_f within 20% of τ_s, or ξ at the skew of the lognormal equivalent.
- **(FA2)** It can't fit S3 (10 s) and S2 within 2 × sd_days at the same time, in-sample.
- **(FA3)** τ_s or w varies by more than 50% across the leave-one-day-out folds, or sits at a bound in more than one fold.
- **(FA4)** More than 0.1% of M samples are clipped.

**B:**
- **(FB1)** B3 can't fit S2 within 2 × sd_days.
- **(FB2)** The states aren't identifiable: levels merge, or EM runs from different starting points disagree beyond 2 × sd_days.
- **(FB3)** It shows a top/bottom persistence asymmetry (S4) more than 2 × sd_days beyond Azure's.

**D:**
- **(FD1)** Expected to fail F0 or FA2-like checks. If D passes, parsimony selects it.

## 10. Conditions before Wednesday may be opened

1. This preregistration, with all its amendments, is committed.
2. At least one eligible candidate passed the internal rule. **If none did, Cycle 2 stops and Wednesday stays closed.**
3. Exactly one candidate is selected under section 8.
4. That candidate is refitted on all six development days with the section 4 procedure, and its parameters are frozen.
5. **A freeze record is committed,** listing:
   - the class and parameters
   - the reference file hashes
   - `traffic_model_sha256` and `generator_sha256`
   - the analysis-code commit
   - the acceptance criteria and tolerances
   - the scenario rule
6. **The holdout gate is updated for Cycle 2,** reading the internal-validation result. It's tested with synthetic fixtures only and recorded in the freeze record.
7. **The owner gives explicit written authorisation** in a separate message.
8. **Wednesday is evaluated exactly once.** The script refuses if the output exists. The result is recorded whether it passes or fails, and a failure isn't tuned against or rerun within Cycle 2.

**Open before candidate fitting** (to be settled by amendment):
- Which checks *gate* on Wednesday. Proposed: the queue test, with all three criteria and no catastrophic cell. The S1–S4 band comparisons at frozen tolerances would be reported, and a band failure would limit the descriptive claim.
- Whether S1 band checks should also gate internally. Under Q3 they're reported only.

---

## Amendment 1 (2026-10-05): final queue-validation rule (prospective)

- **Decided by:** hydrangeas20, 2026-10-05. Approves the candidate-independent audit recommendation and authorises freezing the Cycle 2 validation system.
- **Executable form:** `analysis/cycle2_validation.py` (commit `13de097`), tested in `tests/test_cycle2_validation.py`.
- **Freeze record:** `analysis/cycle2_validation_freeze.json`.
- **Supersedes:** section 6's provisional per-cell queue criteria 1 and 2 and the 0.25–4.0 catastrophic bound. Section 7's decision table has been applied (see the provenance below).

### A1.1 The frozen rule

**For each gating fold (Fri 05-10, Mon 05-13, Tue 05-14, Thu 05-16), using its 24 eligible hours:**

**Inputs.** For each hour, each queue cell (s, ρ) ∈ {0.2, 1.0} s × {0.6, 0.8}, and each percentile (p95, p99), the validator takes three values:
- the candidate's median over 20 seeds;
- the Poisson control's median over 20 seeds;
- Azure's value.

A value is **near zero** if it's below 0.01·s (the frozen Cycle 1 definition).

**The four checks:**

| Check | Definition |
|---|---|
| **Aggregate ratio G** | For each of the 8 cell-and-percentile combinations: exp(mean over informative hours of log(candidate / Azure)). An hour is informative if neither value is near zero. G = 1 if no hour is informative |
| **C1′, equivalence** | Each of the 8 G values satisfies **1/1.40 ≤ G ≤ 1.40** (B = 1.40, inclusive) |
| **Near-zero cap** | Hours where exactly one of candidate and Azure is near zero make up **≤ 10%** of the fold's hour × cell × percentile values |
| **Criterion 3** | **Unchanged.** `queueing.judge_cell` with the clarified rule (Cycle 1 Amendment 2, A2.3); the candidate beats the Poisson control in ≥ 80% of non-tie cells, with at least one non-tie cell |

**A fold passes** if C1′, the near-zero cap and criterion 3 all hold.

**Safety, C2′:** a fold violates safety if any of its 8 G lies outside **[0.5, 2.0]** (inclusive bounds).

**Rule:** at least **3 of the 4** gating folds pass, **and** no gating fold violates C2′.

**Not gates:**
- The Azure-vs-Azure (bootstrap) comparison is **report-only**. It cannot affect candidate acceptance or selection, and the validation code doesn't accept it as an input.
- Cycle 1's per-cell criteria 1 and 2 are **rejected** for Cycle 2, and the validation code can't reach them.

### A1.2 Provenance (why this rule, and how it was chosen)

1. **Why the original criteria were rejected.** The original per-cell criteria 1 and 2 were rejected because candidate-independent, perfect-model auditing showed they were **miscalibrated**: a model equal to the truth passed the 3-of-4 rule in 0 of 50 replicates ([criterion audit](phase-2-cycle-2-criterion-audit.md), sections 1–2).
2. **No Cycle 2 candidate had been fitted or evaluated** before this amendment. None has been to this day.
3. **How B was chosen.** B = 1.40 was selected by the decision rule written down *before* the 200-replicate run (audit doc, section 4): the smallest predeclared bound whose 95% lower limit on the perfect-model pass rate is ≥ 0.80 under both truth processes. The predeclared bounds were {1.25, 1.30, 1.35, 1.40}, with no search outside them.
   - **B = 1.40 met that rule:** lower limits 0.851 (C1 truth) and 0.811 (bootstrap truth).
   - **B = 1.35 failed it:** lower limits 0.755 and 0.734, and the bootstrap point estimate (0.795) is below 0.80.
4. **Candidate results played no role** in selecting any criterion; there are none.
5. **The other rules were audited separately** under the 200-replicate null (audit doc, section 7):
   - **Safety bound:** family-level false failure 0.000 and 0.010.
   - **Near-zero cap:** 0 false failures in 800 folds per truth.
   - **Criterion 3:** any-fold failure 0.020 and 0.000.
6. **Azure-vs-Azure stays report-only**, because its bootstrap is biased upward.
7. **This amendment is prospective for all Cycle 2 candidates** (D1, A1, A2, B2, B3) and binds their internal validation.
8. **Cycle 1's historical result is unchanged.** It remains a failed validation cycle, subject to the dated methodological note on criteria 1 and 2 already added to the Cycle 1 record.
9. **The criteria won't change because a candidate fails.** Any later change needs a new dated amendment, justified independently of candidate results, and committed before the run it affects.

### A1.3 Measurement resolution (frozen; binding on every claim)

The validator **does not establish close distributional equality, or queue fidelity to within ±10–15%.** Under the 200-replicate perfect-model audit at B = 1.40:

| Bias | Detection |
|---|---|
| About 1.15× | **Generally not detected** (8–13% globally) |
| About 1.25× | **Limited, inconsistent power** (44–46% globally) |
| About 1.30× | Detected **71–73%** of the time globally |
| 1.50× | Detected **essentially always** globally (100%) |
| 1.50× confined to one cell-and-percentile | Materially lower but still useful power: **63–100%**, depending on the cell |

**Wording for a passing candidate:**
- **Supported:** "No queue-behaviour discrepancy was detected at the resolution supported by the preregistered validation procedure."
- **Not allowed:** describing a passing candidate as "matching Azure".
- **Stronger quantitative wording** must be supported explicitly by the audit.

The same statement is held verbatim in `cycle2_validation.RESOLUTION_STATEMENT` and returned with every validation result.

### A1.4 Still open (unchanged by this amendment)

- **Section 5:** the band tolerances (computed from development data before candidate fitting).
- **Section 10:** which checks gate on Wednesday.
