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
- **Freeze record:** `analysis/cycle2_validation_freeze.json`, added in **freeze commit `0de6f704e0613cebd7bfad872b5665ae454acc81`**. The file's SHA-256 is `2bda4bf273d57dd487d38e8ff9231ef7a3e9f07f90fb2e26e52f8b58771cab30`. The commit SHA is recorded here, after the fact, because a commit can't contain its own SHA.
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

---

## Amendment 2 (2026-10-05): S1 tolerances frozen; pre-fit ambiguities for Candidate D

- **Authorised by:** hydrangeas20, 2026-10-05 (Candidate D stage, Stage 0).
- **Committed:** before any Candidate D code, fit or result exists.
- **Status:** **S1 tolerances FROZEN. Candidate D NOT STARTED.** Stage 0 stopped on the ambiguities in A2.2, as instructed: "If the existing preregistration does not uniquely determine how any tolerance should be calculated, STOP and report the ambiguity."

### A2.1 S1 band tolerances (frozen)

**Method.** Section 5, which is Cycle 1 §6.1 as implemented in `analysis/azure_traffic.py` (`tolerances`):
- For each rate band, use each development day with **≥ 3 eligible hours** in that band.
- That day's pooled curve is √max(element-wise median over its band hours of CV²(W), 0), for W ∈ {1, 2, 5, 10, 30, 60} s.
- The tolerance is **2 × the maximum over windows of the across-day SD (ddof = 1)**.
- A band qualifies only with **≥ 3** such days.

**Implementation check.** `analysis/cycle2_tolerances.py` (commit `5e6b491`; file SHA-256 `deada822…`), applied to the five training days alone, reproduces Cycle 1's recorded tolerances exactly: 0.0985, 0.0321, 0.0146 and 0.0035.

| Band | Eligible hours (Fri, Sat, Sun, Mon, Tue, Thu) | Qualifying days | Qualifies | **Tolerance** |
|---|---|---|---|---|
| 3–10 rps | 5, 8, 10, 5, 5, 4 | all six | yes | **0.0924** |
| 10–30 rps | 9, 15, 14, 8, 8, 10 | all six | yes | **0.0315** |
| 30–60 rps | 9, 0, 0, 5, 4, 4 | Fri, Mon, Tue, Thu | yes | **0.0128** |
| 60–120 rps | 1, 0, 0, 6, 7, 6 | Mon, Tue, Thu | **yes, on its own** | **0.0065** |

- **The 60–120 band qualifies on its own.** So **the Cycle 1 merged 30–120 workaround is retired for Cycle 2.** The Cycle 1 method and results are unchanged as history.
- **Frozen in:** `cycle2_config.S1_TOLERANCES`. Tested in `tests/test_cycle2_tolerances.py`: the values, the support rule, the method on synthetic data, the cache provenance, and local recomputation.
- **Data:** `analysis/results/cycle2/tolerances-s1.json` (SHA-256 `1a2fb042…`), computed from `training.npz` (`1f0e15da…`) and `validation.npz` (`47ea7ddf…`), cache-only. No Wednesday or raw data.
- **Role.** The S1 tolerances are used for the S1 band comparisons that section 6 reports during internal validation. They don't gate: the frozen queue rule (Amendment 1) is the gate.

### A2.2 Ambiguities that must be resolved before Candidate D can be fitted

The preregistration doesn't determine each of the following uniquely. None has been resolved by a discretionary choice. **No S2–S4 dispersion has been computed**, so whatever resolution is chosen can't be influenced by those values.

1. **S2–S4 tolerances (section 5: "the same method gives tolerances for S2–S4").** "2 × the maximum over windows" has no unique analogue:
   - **S3** mixes components on different scales (skewness, excess kurtosis, standardised quantiles), so a maximum across them is dominated by kurtosis.
   - **S2** (7 lags) and **S4** (top and bottom tail × 5 lags) could take the maximum over lags, over tails, or not at all.

   Candidate readings:
   - (a) a tolerance per statistic component: 2 × its across-day SD, with no maximum;
   - (b) 2 × the maximum within same-scale families (S2 over lags; S4 over lags, per tail; S3 per component);
   - (c) don't define S2–S4 tolerances, and report S2–S4 against 2 × sd_days, the quantity section 9's falsification rules already use.

   These tolerances are reporting-only; section 9 uses 2 × sd_days. But the instruction is to stop rather than choose.
2. **Optimiser starting points.** Section 4 says "8 preregistered starting points", but none are listed anywhere.
3. **Optimiser budget and parameterisation:**
   - whether the 8 start evaluations count within the 300-evaluation budget;
   - whether Nelder–Mead runs from the best start only, or from several;
   - the parameter space (for example log a, b, log τ) and any bounds;
   - the termination tolerances.
4. **sd_days during leave-one-day-out:**
   - whether sd_days (and its floor) is fixed from all six days, or recomputed from each fold's five training days;
   - if recomputed: the 60–120 band has only 2 qualifying days in the Mon, Tue and Thu folds, so how does that band enter the loss? Excluded; the 2-day SD; or the six-day value?
5. **Calibration seeds:** which 3 seeds per hour in the calibration range (1,000,000–1,999,999), and how they map to hours and folds.
6. **Validation seeds:** which 20 seeds per cell, for the candidate and for the Poisson control, in the validation range (2,000,000–2,999,999).
7. **Observed rate range and scenario during fitting and validation.** Is σ(λ)'s observed range the Cycle 1 training range [3.20, 82.83] rps, or recomputed from the six development days? And is the `edge` scenario used when a within-hour trend leaves it, as Cycle 1 §7 and the Cycle 2 audit did?
8. **S1 pooling with an even number of hours.** Should S1 be the median of √CV² or √ of the median CV², as Cycle 1 pools? These differ only when a band has an even number of hours.
9. **D's falsification sequence (section 9).** FD1 ("expected to fail F0 or FA2-like checks") is written as an expectation, not as an explicit pre-queue rejection rule, and "FA2-like" isn't defined for D. As written, no rule explicitly rejects D before queue validation; F1 applies only after it. Please confirm that D proceeds to leave-one-day-out queue validation whatever its in-sample S1–S4 fit, with in-sample misfit reported as a diagnostic.

**Next step:** a dated Amendment 3, committed before any D code runs, that resolves items 1–9.

---

## Amendment 3 (2026-10-06): Candidate D procedure, resolving the Amendment 2 ambiguities

- **Decided by:** hydrangeas20, 2026-10-06.
- **Committed:** before any S2–S4 value, any Candidate D code, and any D fit or result.
- **Status:** definitions below are FROZEN, **except the numeric parameter bounds (A3.10)**. Those are PROPOSED and await the owner's decision. The start points depend on the bounds (A3.2). Candidate D can't be fitted until A3.10 is frozen.

### A3.1 S2–S4 reporting tolerances (resolves Amendment 2 item 1)

- **One tolerance per statistic component, per band:** 2 × the across-day SD (ddof = 1) of that day's band-pooled value.
  - It uses days with ≥ 3 eligible hours in the band, and the band must have ≥ 3 such days.
  - A day's band-pooled value is the element-wise median over the day's eligible hours in that band.
  - There's no maximum across components, and no floor.
- **Components:**

  | Statistic | Components |
  |---|---|
  | S2 | `acf_{1,2,5,10,20,30,60}` |
  | S3 | for W = 10 s and W = 5 s: `skew`, `excess_kurtosis`, `zq{0.01,0.05,0.95,0.99,0.999}`. (`m*_sd` is a scale statistic, not part of S3, and is excluded) |
  | S4 | `persist_{top,bottom}_{1,2,5,10,20}` |

- **These tolerances are descriptive and reporting-only.** They don't alter the frozen queue-validation verdict.

### A3.2 Optimiser starts (resolves item 2)

- **Exactly eight deterministic starts**, in transformed coordinates θ = (log a, b, log τ).
- **Starts 1–7:** a fixed design in the unit cube, mapped linearly onto the frozen bounds (A3.10):
  - the centre (½, ½, ½);
  - six axial points that set one coordinate to 0.1 or 0.9 and leave the others at ½.
- **Start 8:** the historical Cycle 1 C1 fit, a = 0.4406544452547643, b = −0.32313480634892916, τ = 9.23892541130273 s, taken from `traffic/reference/azure_code_burstiness.json`.
- **No start is chosen using D's objective.**

### A3.3 Optimiser (resolves item 3)

- **Budget:** 300 objective evaluations **in total**, counting the 8 starts.
- **Procedure:** evaluate all 8 starts, take the lowest-objective one (ties go to the lower start number), and run Nelder–Mead from it alone.
- **Implementation:** an in-repository Nelder–Mead (`analysis/cycle2_optimizer.py`; no new dependency):
  - **Coefficients:** reflection 1, expansion 2, contraction 0.5, shrink 0.5.
  - **Initial simplex:** the start, plus one vertex per coordinate displaced by 10% of that coordinate's bound width. The displacement is toward the upper bound, or toward the lower bound if the upper bound would be exceeded.
  - **Bounds:** every trial point is clipped to the bound box.
  - **Convergence:** stop when (max f − min f over the simplex) ≤ 1e-4 **and** the maximum coordinate spread ≤ 1e-4, or when the 300-evaluation cap is reached.
- **Result:** the fit is the best finite point among **all** evaluations, starts included. The termination reason is recorded.

### A3.4 Failure and recovery, and D's progression (resolves item 9; supersedes FD1 for D)

- **Invalid evaluations.** An objective evaluation is invalid if it's non-finite, or if generation or the statistics raise an error. It's recorded and counts as +∞. A start at +∞ can't be selected.
- **Invalid fits.** A fit is **invalid** if all eight starts are +∞, if its best objective is non-finite, or if its parameters lie outside the bounds.
- **No rescue.** No recovery is attempted: no restarts, perturbations or second runs.
- **D proceeds through full leave-one-day-out queue validation** unless the procedure itself is invalid:
  - If the full-development fit is invalid, D is labelled **INVALID PROCEDURE** and stops.
  - If a fold's fit is invalid, that fold is recorded as **failing** and its queue test isn't run.
- **Descriptive S1–S4 inadequacy never stops D.** It's reported explicitly, and the frozen queue validator decides D's operational verdict.
- **FD1's undefined "FA2-like" early rejection doesn't apply to D.**
- **D's label** is one of **PASS**, **FAIL** or **INVALID PROCEDURE**. There's no pre-queue structural falsification rule for D.

### A3.5 Calibration targets and weights in leave-one-day-out (resolves item 4)

**For fold d, the training days are the six development days without d.** The held-out day influences neither the fold's targets nor its ordinary dispersion.
- **Target s_obs(b, c):** the band-pooled value over all eligible band-b hours on the training days. For S1, that's √max(median CV², 0) (A3.7).
- **Weight sd(b, c):** the across-day SD (ddof = 1), over training days with ≥ 3 eligible hours in b.
- **Fallback:** if fewer than 3 training days qualify for band b, sd(b, c) = the **frozen full-development SD** for (b, c), computed under the same rule over all six days. **Every fallback is recorded in the candidate report.**
  - From the frozen eligibility counts, the expected fallbacks are the **60–120 rps band** (all its components) in the **Mon, Tue and Thu folds**. No others are expected.
- **Floor:** 0.25 × the median over the four bands of the (post-fallback) sd for that component, as in section 4.
- **Loss:** Σ_b Σ_c ((ŝ_sim − s_obs)/sd)², over the 30 target components per band:
  - S1 at the 6 windows;
  - S2 at the 7 lags;
  - S3 at W = 10 s: skewness, excess kurtosis and the 5 standardised quantiles;
  - S4: top and bottom tails at the 5 lags.
- **A band with no eligible training hours** is left out of that fold's loss and recorded.
- **The full-development fit**, used for in-sample reporting and later for the Wednesday model, uses all six days under the same rules.

### A3.6 Seeds (resolves items 5–6)

**Derivation.** seed = the first 8 bytes, big-endian, of SHA-256(`namespace|i1|i2|…`), used as `numpy.random.default_rng(seed)` (`analysis/cycle2_seeds.py`, tested).

**Namespaces:**

| Stream | Namespace | Indices |
|---|---|---|
| D calibration | `relay/cycle2/D/calibration/v1` | (fit, day, hour, replicate 0–2), where fit ∈ {`all`, held-out day}. The same seeds are used for every θ within a fit (common random numbers) |
| D validation | `relay/cycle2/D/validation/v1` | (held-out day, hour, cell 0–3, replicate 0–19) |
| Poisson-control validation | `relay/cycle2/poisson-control/validation/v1` | (held-out day, hour, cell 0–3, replicate 0–19) |

The streams don't overlap: tests enumerate every planned seed in all three and require them all to be distinct.

### A3.7 S1 pooling (resolves item 8)

The Cycle 1 estimator, exactly: √max(median(CV²), 0). Not the median of √CV².

### A3.8 Rate range and out-of-range behaviour (resolves item 7)

- **Observed range:** the minimum and maximum mean rate of eligible hours over all six development days (the Cycle 1 §4 definition). It's computed and frozen under this amendment.
- **Inside the range,** σ(λ) = a·λ^b.
- **Outside it, within an hour's trend:** only σ extrapolates, by the same power law (the frozen `trend` principle), and τ is unchanged. No new structural behaviour is inferred.
- **Reporting:** every out-of-range evaluation is reported, as the fraction of 0.1 s bins out of range per hour.
- **Change from precedent:** this replaces the `edge` scenario that Cycle 1 §7 and the Cycle 2 audit used.

### A3.9 Validation procedure for D

For each fold (gating: Fri, Mon, Tue, Thu; reported: Sat, Sun):
- **Simulation:** each eligible hour of the held-out day is simulated on its own trend (the 600 s moving average of Azure's per-second counts).
- **Model value per cell:** the median p95/p99 over 20 validation seeds per cell (A3.6). The Poisson control is built the same way from its own namespace.
- **Servers:** c = ⌈λ_ref·s/ρ⌉, with λ_ref the Azure hour's mean rate.
- **Verdict:** the gating folds go to the **frozen** `cycle2_validation.validate`, and its resolution statement is returned with the result.
- **Rate-band holdouts** (reported only): refit on all six days without band b's hours in the loss, and report the S1 error for band b against its frozen S1 tolerance.

### A3.10 Parameter bounds: PROPOSED, NOT FROZEN (stop condition)

The repository supports the τ bound but not the a and b bounds, so these need the owner's decision. The proposal and its justification are in the addendum below this section, which is committed together with the computed values.

### A3.11 No post-result rescue

D gets exactly one preregistered fitting and evaluation procedure. Once any D result has been observed, none of these change:
- its starts, bounds, loss, weights or seeds
- its tolerances, optimiser or model structure
- the validator

No D2 or D3 is created unless separately authorised as a new prospective experiment.
