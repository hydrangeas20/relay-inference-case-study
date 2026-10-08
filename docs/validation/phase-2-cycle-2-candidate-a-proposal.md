# Phase 2, Cycle 2: Candidate A specification and plan (PROPOSED, NOT FROZEN)

- **Prepared:** 2026-10-08, under the owner's authorisation for Candidate A specification, implementation planning and prospective preregistration **only**.
- **Status:** **PROPOSAL.** Nothing here is frozen.
  - Once the owner approves, the frozen form becomes a dated Amendment 4 to the [preregistration](phase-2-cycle-2-preregistration.md), committed with an executable configuration and tests, before any Candidate A code runs on data.
  - **No Candidate A code exists.** Nothing has been fitted, simulated, generated or evaluated.
  - Candidate B hasn't been started.
- **Context:** Candidate D has completed its frozen procedure with an internal **PASS** (3 of 4 gating folds; [ledger](phase-2-cycle-2-candidate-ledger.md), including the D.7 correction). D is the **provisional parsimonious default** (section 8).

**Purpose of A.** To test whether controlling temporal dependence (two OU timescales) and marginal shape (a lighter-tailed, skew-controlled Gaussian-copula link) **independently** improves S1–S4 fidelity, while preserving queue adequacy under the frozen validator.

- This is the primary class chosen on 2026-09-29 ([diagnosis memo](phase-2-queueing-diagnosis.md), section E) and specified on 2026-10-02 (preregistration section 3).
- Nothing here is derived from D's residuals.

---

## 1. What was specified before D's results

D's first result was committed in `68e008a`/`dbc25ea` on 2026-10-08. Everything in 1.1 and 1.2 predates it.

### 1.1 Frozen (preregistration skeleton `196074a`, 2026-10-02; Amendment 1, 2026-10-05)

| Item | Frozen text | Where |
|---|---|---|
| Generator | Shared by all classes. For each 0.1 s bin k, Nₖ ~ Poisson(λₖ·Mₖ·Δ), with E[M] = 1. Classes differ only in M. In every class, σ(λ) = a·λ^b inside the observed range | §3 |
| A1 | Y = √w·F + √(1−w)·S, where F and S are independent unit-variance OU processes (τ_f < τ_s), updated exactly per bin. M = Q_{σ,ξ}(Φ(Y)), where Q is a mean-1 standardised sinh-arcsinh quantile function with SD σ(λ), skewness parameter ξ, and tail weight fixed at Gaussian. Clipped at 0.02. Parameters (6): a, b, ξ, w, τ_f, τ_s | §3 |
| A2 | As A1, with ξ(λ) = c·λ^d. Parameters (7) | §3 |
| Variant cap | At most five variants get internal validation (D1, A1, A2, B2, B3). A1 and A2 are both within the cap | §3 |
| Out of range (Q8) | Only σ(λ) extrapolates (`trend`). ξ, w, τ_f and τ_s are held at their boundary values. The traffic is labelled PROJECTED | §3 |
| Statistics and loss | S1–S4 targets; S5 diagnostic only; queue metrics never enter the loss. Loss = Σ_bands Σ_S1–S4 ((ŝ_sim − s_obs)/sd_days)², with 3 seeds per hour and common random numbers across θ | §4 |
| Optimiser | 8 preregistered starting points, then Nelder–Mead, with **at most 300 loss evaluations per fit** | §4 |
| Internal validation | Leave-one-day-out. Gating folds Fri, Mon, Tue, Thu; Sat and Sun reported | §6 |
| Queue rule | The frozen aggregated validator, B = 1.40, unchanged. "Prospective for all Cycle 2 candidates (D1, A1, A2, B2, B3)" | Amendment 1, A1.2 item 7 |
| Selection | Default: fewest effective parameters. A more complex candidate is chosen only if it "passes all three criteria in **more gating folds** than the simpler one". The highest criterion-1 fraction isn't a criterion | §8 |
| Falsification | F0: fails the internal rule. F1: fits in-sample within 2 × sd_days but fails the queue test. FA1–FA4 (section 6 below) | §9 |
| Tolerances | S1 (Amendment 2), and S2–S4, rate range, dispersion and fallback values (Amendment 3, frozen data values) | A2, A3 |

**Amendment 3's procedure is written for D.** A3.1, A3.5, A3.7 and A3.8 define data quantities and rules that aren't specific to D. A3.2–A3.4, A3.6, A3.9 and A3.11 say "D" explicitly. **Proposal:** adopt each of them for A, unchanged, by explicit reference (section 4).

### 1.2 Proposed before D, but not frozen (diagnosis memo, 2026-09-29, section E)

- **Timescales:** "τ of roughly 1–3 s and 20–60 s" for the fast and slow OU processes.
- **Link examples:** softplus, a truncated linear max(ε, 1 + σY), or "a skew parameter fitted to the 5–10 s rate distribution". The preregistration later fixed the sinh-arcsinh copula link, so these examples are superseded.
- **Identifiability:** "timescales weakly identified".

### 1.3 Not specified anywhere (genuine gaps; section 8 lists the decisions)

1. The exact sinh-arcsinh parameterisation and sign convention; how the mean-1 standardisation is computed; whether M is renormalised after clipping.
2. The coordinates, the bounds for every parameter, and how τ_f < τ_s is enforced.
3. The eight starting points for 6 and 7 dimensions.
4. Whether the 300-evaluation cap (§4) counts the starts, and whether it's adequate in 6–7 dimensions.
5. Seed namespaces for A, and whether A1 and A2 (and the Poisson control) share streams.
6. A2: the reference rate for c, the bounds for c and d, and ξ outside the range.
7. Operational definitions of FA1–FA4, which fit(s) they're evaluated on, and whether they apply per variant or per class.
8. Whether an FA rejection stops queue validation or is reported alongside it, and the verdict labels.
9. How section 8's "passes all three criteria" maps onto Amendment 1's fold pass.

---

## 2. Candidate A: precise model (proposed form of the frozen definition)

**Notation.**
- Δ = 0.1 s.
- λₖ: the hour's expected rate in bin k (the 600 s moving-average trend, as for D).
- [λ_lo, λ_hi] = [3.2, 82.82805555555555] rps: the frozen range (A3.8).
- λ̄ₖ = clip(λₖ, λ_lo, λ_hi).

**Arrivals** (shared generator, as D):
- Nₖ ~ Poisson(λₖ·Mₖ·Δ).
- Arrival times are uniform within their bin.

**Dependence (two OU timescales, exact per-bin discretisation).**
- φ_f = e^(−Δ/τ_f), and φ_s = e^(−Δ/τ_s).
- F₀, S₀ ~ N(0, 1) (stationary start).
- Fₖ = φ_f·Fₖ₋₁ + √(1 − φ_f²)·εₖ, and Sₖ = φ_s·Sₖ₋₁ + √(1 − φ_s²)·ηₖ, with ε and η i.i.d. N(0, 1).
- Yₖ = √w·Fₖ + √(1−w)·Sₖ.
- Then Y is stationary N(0, 1) with Corr(Yₖ, Yₖ₊ₗ) = w·e^(−lΔ/τ_f) + (1−w)·e^(−lΔ/τ_s).

**Marginal (Gaussian copula, sinh-arcsinh, tail weight δ = 1).** The SHASH variate with skewness parameter ξ and δ = 1 is X = sinh(asinh(Z) + ξ), Z ~ N(0, 1) (Jones & Pewsey 2009).
- **Copula:** its quantile at u = Φ(Y) is sinh(asinh(Y) + ξ). So Q(Φ(Y)) needs no numerical inversion: Φ and Φ⁻¹ cancel exactly.
- **Closed-form moments** (δ = 1):
  - μ(ξ) = K·sinh ξ;
  - s²(ξ) = cosh²ξ + 2·sinh²ξ − K²·sinh²ξ;
  - K = E√(1 + Z²) = 1.3545308064813264, a constant (computed by 200-node Gauss–Hermite and checked against Monte Carlo in tests).
- **Multiplier:**
  - M̃ₖ = 1 + σ(λₖ)·[sinh(asinh(Yₖ) + ξₖ) − μ(ξₖ)] / s(ξₖ);
  - Mₖ = max(M̃ₖ, 0.02).
- Before clipping, E[M̃] = 1 and SD(M̃) = σ(λ). That's the same meaning of σ as in D, where σ is the SD of the lognormal multiplier.
- **Sign convention:** ξ > 0 gives right skew; ξ = 0 gives the Gaussian copula (symmetric M).
- **Attainable skewness:** with δ = 1 it saturates, approaching about 1.44 in absolute value as |ξ| → ∞. Examples: ξ = ±0.25 → ±0.41; ±0.5 → ±0.75; ±1 → ±1.17; ±2 → ±1.40.

**Rate dependence.**
- **σ:** σ(λ) = a·λ^b for all λ, including outside the range (`trend`, A3.8 and Q8).
- **ξ in A1:** a constant.
- **ξ in A2:** ξₖ = c·(λ̄ₖ/λ_ref)^d, with λ_ref = √(λ_lo·λ_hi) = 16.28034943659926 rps.
  - This is the frozen c·λ^d with c re-expressed at the reference rate: c_frozen = c·λ_ref^(−d). The reparameterisation is exact and only makes c's bounds interpretable.
  - ξ uses λ̄ (clipped), so it's held at its boundary value outside the range (Q8).
- **w, τ_f, τ_s:** constants, so they're trivially "held" outside the range.

**Clipping.** Proposed: no renormalisation after clipping. That's the frozen text ("clipped at 0.02"), and FA4 caps clipping at 0.1% of samples. Decision DA1.

---

## 3. Parameters

| Variant | Free parameters | Meaning |
|---|---|---|
| A1 (6) | a, b | Multiplier SD σ(λ) = a·λ^b (as D) |
| | ξ | Copula skewness parameter (marginal shape; δ fixed at 1) |
| | w | Variance share of the fast OU component |
| | τ_f, τ_s | Fast and slow correlation times, τ_f ≤ τ_s |
| A2 (7) | a, b, w, τ_f, τ_s | As A1 |
| | c, d | ξ(λ) = c·(λ̄/λ_ref)^d: c is ξ at 16.28 rps; d is its rate exponent |

**Nesting.** Two degeneracies:
- **Single timescale:** w ∈ {0, 1}, or τ_f = τ_s.
- **Rate-independent ξ:** d = 0, which makes A2 equal to A1.

Neither reproduces D exactly: D's lognormal marginal isn't a δ = 1 SHASH marginal. The closest A analogue of D's marginal is ξ_LN(σ), the ξ whose skewness equals the lognormal skewness σ(σ² + 3) (sections 6 and FA1).

---

## 4. Proposed fitting procedure

### 4.1 Coordinates and bounds (DA2, DA3)

| Coordinate | Bounds | Basis |
|---|---|---|
| log a | [log 0.05, log 5] | Option W, owner-approved for D (2026-10-07); same meaning of σ |
| b | [−1.0, 0.5] | Option W |
| ξ (A1), or c (A2) | [−2, 2] | Mathematical: δ = 1 SHASH skewness saturates, and ±2 reaches ±1.40 of the attainable ±1.44. Includes 0 (symmetric) and ξ_LN over the range at the Cycle 1 C1 σ (0.19 at 82.8 rps to 0.67 at 3.2 rps) |
| d (A2) | [−1, 1] | Discretionary. At \|d\| = 1, ξ changes by up to 5.1× either side of λ_ref, or 25.9× end to end (λ̄/λ_ref ∈ [0.197, 5.09]). 0 is the A1 nesting point |
| w | [0, 1] | The full mathematical range, so a collapse to one timescale (FA1) is reachable and detectable at a bound. A logit coordinate couldn't reach 0 or 1 |
| log τ_f | [log 0.1, log 600] | The repository's τ estimator grid (`stats.TAU_GRID_S`), as for D's τ |
| u | [0, 1] | log τ_s = log τ_f + u·(log 600 − log τ_f). This guarantees τ_f ≤ τ_s ≤ 600 s for every point in the box. u = 0 is τ_s = τ_f (FA1 collapse) |

**Alternative for DA2:** separate, ordered ranges, informed by the memo's pre-D "1–3 s / 20–60 s": τ_f ∈ [0.1, 10] s and τ_s ∈ [10, 600] s, in log coordinates. This builds the timescale separation into the bounds (so the box enforces ordering), but makes FA1's "τ_f within 20% of τ_s" reachable only near 10 s.

**Feasibility.** Not every point in the box yields usable traffic: for example, a large a with b > 0 clips heavily. Points whose statistics are non-finite are invalid evaluations (+∞, A3.4), as for D. The box doesn't exclude them.

### 4.2 Starts (DA4)

**Proposal:** exactly 8 deterministic starts, following A3.2's pattern of seven space-filling points plus the historical Cycle 1 point.

- **Starts 1–7:** rows 1–7 of the Sylvester Hadamard matrix H₈, entry (i, j) = (−1)^popcount(i AND j).
  - Columns 1–6 are used for A1 and columns 1–7 for A2.
  - Each entry maps to the unit level 0.5 ± 0.3 (that is, 0.2 or 0.8), then linearly onto the bounds.
  - **Properties:** every coordinate takes each level 3 or 4 times; the 7 points are distinct; and every pair of coordinates is nearly orthogonal (|inner product| = 1 over 7 runs).
- **Start 8:** the Cycle 1 C1 fit carried into A's structure, using no Cycle 2 result:
  - a = 0.4406544452547643, b = −0.32313480634892916;
  - τ_f = τ_s = 9.23892541130273 s (u = 0), w = 0.5;
  - ξ = ξ_LN at λ_ref = 0.33848 (A2: c = 0.33848, d = 0).

  Here ξ_LN is the δ = 1 SHASH ξ whose skewness equals C1's lognormal skewness σ(σ² + 3) at σ = a·λ_ref^b = 0.17888, which is 0.54237.

Rounded (a, b, ξ or c, d, w, τ_f, τ_s); exact θ values will be frozen in configuration:

| Start | A1 (a, b, ξ, w, τ_f, τ_s) | A2 (a, b, c, d, w, τ_f, τ_s) |
|---|---|---|
| 1 | 0.1256, 0.2, −1.2, 0.8, 0.5697, 149.2 | 0.1256, 0.2, −1.2, 0.6, 0.2, 105.3, 149.2 |
| 2 | 1.991, −0.7, −1.2, 0.8, 105.3, 149.2 | 1.991, −0.7, −1.2, 0.6, 0.8, 0.5697, 2.292 |
| 3 | 0.1256, −0.7, 1.2, 0.8, 0.5697, 2.292 | 0.1256, −0.7, 1.2, 0.6, 0.2, 0.5697, 149.2 |
| 4 | 1.991, 0.2, 1.2, 0.2, 0.5697, 2.292 | 1.991, 0.2, 1.2, −0.6, 0.2, 0.5697, 2.292 |
| 5 | 0.1256, 0.2, −1.2, 0.2, 105.3, 149.2 | 0.1256, 0.2, −1.2, −0.6, 0.8, 0.5697, 149.2 |
| 6 | 1.991, −0.7, −1.2, 0.2, 0.5697, 149.2 | 1.991, −0.7, −1.2, −0.6, 0.2, 105.3, 423.7 |
| 7 | 0.1256, −0.7, 1.2, 0.2, 105.3, 423.7 | 0.1256, −0.7, 1.2, −0.6, 0.8, 105.3, 149.2 |
| 8 | 0.4407, −0.3231, 0.3385, 0.5, 9.239, 9.239 | 0.4407, −0.3231, 0.3385, 0, 0.5, 9.239, 9.239 |

**Alternatives for DA4:**
- levels 0.5 ± 0.2, which keeps starts further from implausible σ values;
- the centre (½, …, ½) in place of one Hadamard row;
- A3.2's axial pattern. In 6–7 dimensions that can only cover one side of each coordinate.

**Cycle 1 vs Cycle 2 information.** Start 8 uses Cycle 1's C1, which is pre-Cycle-2 history (as A3.2 did). No start uses D's fitted values.

### 4.3 Optimiser and budget (DA5)

**Reused, unchanged:** the frozen optimiser module `analysis/cycle2_optimizer.py` (hash-pinned).
- Its `fit` function is dimension-agnostic.
- Settings: Nelder–Mead coefficients 1/2/0.5/0.5; initial simplex step 10% of each bound width; clipping to the box; FTOL = XTOL = 1e-4 (in coordinate units, so w and u are in [0, 1] units); the result is the best finite point over all evaluations.
- **Procedure (A3.3):** evaluate the 8 starts, take the lowest (ties go to the lower number), and run Nelder–Mead from it alone.

**Budget:** §4 freezes "at most 300 loss evaluations per fit" for every class. Proposal: 300 in total, starts included, exactly as A3.3. Two risks the owner should weigh, without changing the cap unless she decides to:
- **The cap is likely to bind.** In 3 dimensions D took 128–168 evaluations. In 6–7 dimensions, Nelder–Mead may reach the cap before its convergence test is met.
- **Reaching the cap is not a failure.** A3.4 counts a fit at the cap as valid (best finite point), so the termination reason will matter for interpretation (A3 addendum 2's optimiser-versus-model-family requirement).

A prospective change would need a dated amendment justified independently of A's results. The only information behind this concern is D's evaluation counts, which is procedural, not fit quality.

### 4.4 Targets, weights, fits (adopting A3.1, A3.5, A3.7, A3.8 and A3.9 unchanged)

- **Targets and loss** (A3.5): the same frozen targets, weights, floor, fallback and loss as D (`cycle2_targets`, hash-pinned).
  - These depend only on the Azure data and the fold, so **A and D are fitted against identical targets and weights.**
  - Fallbacks are as for D: 60–120 rps in the Mon, Tue and Thu folds.
- **The 11 fits per variant, as for D:**
  - `all`;
  - six leave-one-day-out fits;
  - four `without-band-<b>` fits (reported only).
- **D's implementation readings R1–R5 apply unchanged:**
  - pooling of simulated hour-replicates;
  - held-out descriptive seeds;
  - band-holdout scoring;
  - invalid-fold handling;
  - the 1% boundary proximity.
- **Out of range:** σ extrapolates by its power law; ξ is held at λ̄; w and the τ's are constant. Every out-of-range evaluation is reported as the fraction of 0.1 s bins per hour (A3.8). The fractions are the same as D's, because they depend only on the trend.

### 4.5 Seeds (DA6)

- **Derivation:** `cycle2_seeds.derive_seed`, imported unchanged.
- **New namespaces in a new module.** The frozen `cycle2_seeds.py` isn't edited, so D's pins hold.

| Stream | Proposed namespace | Indices |
|---|---|---|
| A calibration | `relay/cycle2/A/calibration/v1` | (fit, day, hour, replicate 0–2) |
| A validation | `relay/cycle2/A/validation/v1` | (held-out day, hour, cell 0–3, replicate 0–19) |
| Poisson control | **reuse** `relay/cycle2/poisson-control/validation/v1` | as for D |

- **A1 and A2 share A's namespaces** (common random numbers between variants), so their differences reflect parameters, not noise.
- **Reusing the Poisson namespace** makes A's Poisson control **identical** to D's. The comparison against Poisson (criterion 3) is then paired across candidates, and reproducing D's Poisson medians exactly is a built-in check.
- **Tests** enumerate every planned A seed together with all of D's, and require them to be distinct.
- **Alternatives:** separate A1 and A2 namespaces; and/or a separate A Poisson namespace.

---

## 5. Validation procedure (adopting A3.9 and Amendment 1 unchanged)

For each fold:
- **Gating folds:** Fri, Mon, Tue, Thu. **Reported:** Sat, Sun.
- Each eligible hour of the held-out day is simulated on its own trend with that fold's fit.
- **Per (hour, cell):** the median p95/p99 over 20 A seeds and 20 Poisson seeds; the Azure value; servers c = ⌈λ_ref·s/ρ⌉.
- **Verdict:** the gating folds go to the **frozen** `cycle2_validation.validate`, unmodified (B = 1.40, C1′, the near-zero cap, criterion 3, C2′ safety, 3 of 4).
- **Resolution:** the frozen statement applies verbatim to any A pass.

**Fit failures** (A3.4): an invalid full-development fit makes the variant INVALID PROCEDURE; an invalid fold fit is a failing fold. There's no rescue (A3.11).

---

## 6. Falsification rules FA1–FA4 and F1: proposed operational definitions (DA8–DA12)

Section 9 froze these **before D** as rejection rules for class A. Their wording isn't operational. Proposed definitions follow; **each needs the owner's approval.** Variant parameters are those of the named fit.

| Rule | Frozen wording | Proposed operational definition | Evaluated on |
|---|---|---|---|
| FA1 | "The fit collapses to Cycle 1's structure: w at 0 or 1, τ_f within 20% of τ_s, or ξ at the skew of the lognormal equivalent" | Holds if **any** of: (i) w within 1% of the bound width of 0 or 1 (R5); (ii) τ_f ≥ 0.8·τ_s; (iii) the skewness of M̃ at the fitted ξ is within **±0.05** of the lognormal skewness σ(σ² + 3) at the fitted σ(λ_ref). For A2, (iii) is at λ_ref, with ξ = c | Full-development fit |
| FA2 | "It can't fit S3 (10 s) and S2 within 2 × sd_days at the same time, in-sample" | Holds if, in the full-development fit, **any** S2 component or any S3 (W = 10 s) component, in any band, has \|z\| > 2, where z = (sim − obs)/sd and sd is the fit's floored sd_days (strict reading) | Full-development fit |
| FA3 | "τ_s or w varies by more than 50% across the leave-one-day-out folds, or sits at a bound in more than one fold" | Holds if, across the 6 leave-one-day-out fits: (max − min)/median > 0.5 for τ_s, or for w; **or** τ_s or w is within 1% of a bound in ≥ 2 folds | 6 fold fits |
| FA4 | "More than 0.1% of M samples are clipped" | Holds if more than 0.1% of all M̃ₖ values are below 0.02, over every bin of every simulated hour-replicate at the best θ (calibration seeds) | Full-development fit; all fits reported |
| F1 | "Fits its in-sample targets within 2 × sd_days but still fails the queue test" | Holds if every target component in every band has \|z\| ≤ 2 in the full-development fit, **and** the frozen rule fails | Full-development fit + queue verdict |

**Open choices inside these definitions:**
- **FA1 (iii):** the ±0.05 skewness tolerance, and the use of λ_ref, are discretionary. The frozen text gives no tolerance, and ξ_LN depends on λ (0.19–0.67 at C1's σ), so a single "lognormal-equivalent ξ" doesn't exist without one.
- **FA2:** the strict reading may well hold for most fits. D had |z| > 2 on many S2 and S3 components. Alternatives:
  - per band;
  - a majority of components;
  - z computed with the unfloored sd.
- **FA3:** the 50% metric could instead be max/min > 1.5, or the deviation from the median.

**Role of the FA rules (DA12).** Section 9 (frozen) says a class is **rejected** if any rule holds. That's stricter than D's treatment (A3.4 removed FD1's early rejection for D only). Proposal:
- Apply FA1–FA4 and F1 **per variant**. A falsified variant is ineligible for selection and for Wednesday.
- **Still run** the full queue validation and report it, so the operational evidence is recorded regardless.
- Verdict labels:
  - **PASS**: the rule passed and no FA rule holds;
  - **FAIL**: the rule failed;
  - **FALSIFIED (FAx)**: the rule passed but an FA rule holds;
  - **INVALID PROCEDURE**.
- **Alternatives:**
  - FA rules stop the variant before queue validation (the literal "rejected" reading);
  - FA rules are reported only, as D was treated. That would weaken a frozen rule, and would need an explicit amendment.

---

## 7. How A will be compared with D (no change to the frozen rule; no new threshold)

Three axes, reported separately and never combined into one score.

1. **Descriptive fit** (reported; never selects).
   - The same tables as D's ledger, for D, A1 and A2 side by side:
     - in-sample residual z per band and component, Σz² per band, and the count of |z| > 2;
     - the held-out S1-within-tolerance results and S2–S4 within-tolerance counts per fold and band;
     - the band-holdout S1 errors;
     - S5.
   - Targets and weights are identical across candidates, so the z values are on the same scale. Differences are reported as numbers ("in-sample Σz² at 30–60 rps: D 150, A1 …"), with no significance or improvement threshold.
   - The simulation noise differs between candidates (different random streams), so small differences aren't interpreted.
2. **Operational validation** (decides eligibility). The frozen verdict, folds passing, all 8 G per fold, criterion-3 fractions, near-zero and safety, on **identical Azure values** and, under DA6, an **identical Poisson control** to D's.
3. **Complexity.** Effective parameters: D1 3, A1 6, A2 7 (§3).

**Selection** (section 8, frozen before D; mapping DA13):
- **D stays the default.** A variant is selected over D only if all of the following hold:
  - (a) it passes the frozen rule;
  - (b) it isn't falsified (section 6);
  - (c) it passes in **more gating folds** than D.
- D passed 3, so (c) means **4 of 4**.
- "Passes all three criteria in a fold" (§8, written for the superseded per-cell criteria) is read as **"the fold passes under Amendment 1"** (C1′, the near-zero cap and criterion 3). This is a mapping, not a new threshold, and needs approval.
- **A1 versus A2:** the same rule, with A1 as the simpler.
- **Descriptive improvement never selects.**

**Language.** An A result may be described only on each axis separately:
- **Allowed:** "A1 reduced in-sample Σz² in bands X and Y relative to D, and passed the frozen rule in N folds".
- **Not allowed:** "A1 is better than D" or "A1 matches Azure" on descriptive grounds. A passing A carries the frozen resolution statement.

---

## 8. Decisions needed before freezing

| ID | Decision | Proposed | Alternatives |
|---|---|---|---|
| DA1 | Clipping | Clip at 0.02, no renormalisation (frozen text) | Renormalise to mean 1 after clipping |
| DA2 | τ ordering and coordinates | (log τ_f, u), τ_f ≤ τ_s ≤ 600 s | Separate ordered ranges τ_f ∈ [0.1, 10], τ_s ∈ [10, 600] s |
| DA3 | Bounds | §4.1 (Option W for a and b; ξ/c ∈ [−2, 2]; d ∈ [−1, 1]; w ∈ [0, 1]; τ grid) | Narrower ξ; a different d range; λ_ref |
| DA4 | Starts | Hadamard H₈ rows 1–7 at 0.5 ± 0.3, plus the Cycle 1 start | ±0.2 levels; a centre point; the axial pattern |
| DA5 | Budget | 300 per fit, starts included (§4 as written) | A prospective amendment, justified without A results |
| DA6 | Seeds | Shared A1/A2 namespaces; reuse the Poisson-control namespace | Separate namespaces |
| DA7 | Fits | 11 per variant, as D | — |
| DA8–DA11 | FA1–FA4 definitions | Section 6 table | Section 6 alternatives |
| DA12 | Role of the FA rules | Gating per variant; queue validation still run and reported; labels PASS / FAIL / FALSIFIED / INVALID PROCEDURE | Stop before queue; report-only (needs an amendment weakening §9) |
| DA13 | §8 mapping | "Fold passes under Amendment 1" | — |
| DA14 | Variants | Run A1 and A2 in full; both are within the variant cap | Run A1 only. A rule that runs A2 depending on A1's result isn't proposed: it would be results-dependent |
| DA15 | Adopting A3 for A | A3.1, A3.3, A3.4, A3.5, A3.7, A3.8, A3.9 and A3.11, unchanged; A3.2 and A3.6 replaced by 4.2 and 4.5 | — |

**Information audit.** These proposals were written after D's results were known. None uses D's fitted parameters, residuals or verdict:
- the bounds and starts come from Option W (approved for D before its fit), the repository's τ grid, SHASH mathematics and Cycle 1's C1;
- DA5's risk note uses D's evaluation counts, which are procedural information;
- the FA2 note mentions that D had many \|z\| > 2 components. That's to warn that the strict reading is likely to bind; it doesn't propose changing the frozen rule.

---

## 9. Implementation plan (after approval only)

1. **Generator** (`src/relay/traffic/copula.py`, new; shared code under `src/relay/`):
   - two exact AR(1) processes, the Y mixture, the SHASH transform with closed-form μ and s, clipping;
   - the same Poisson binning and within-bin placement as `cox_arrivals`;
   - the existing `generate.py` and `burstiness.py` stay unchanged, so D's recorded generator hashes still describe D;
   - the random-draw order (F innovations, then S, then counts, then uniforms) is recorded in the docstring.
2. **Tests (synthetic only):**
   - E[M̃] = 1 and SD = σ by Monte Carlo;
   - the skewness at ξ against quadrature;
   - Y's lag correlation against w·e^(−l/τ_f) + (1−w)·e^(−l/τ_s);
   - the AR(1) recursion exact against a reference loop;
   - clipping and the FA4 counter;
   - ξ held at λ̄ outside the range;
   - d = 0 makes A2 equal A1 bit for bit under the same seed;
   - w ∈ {0, 1} and u = 0 reduce Y to one OU.
3. **Configuration** (`cycle2_config`): `A_BOUNDS`, `A1_STARTS_THETA`, `A2_STARTS_THETA`, `A_LAMBDA_REF`, `SHASH_K`. Pinned by a new freeze test (`tests/test_cycle2_a_domain.py`), as for D.
4. **Seeds** (`analysis/cycle2_seeds_a.py`): the namespaces in 4.5. A collision test over all D and A seeds.
5. **Runner** (`analysis/cycle2_candidate_a.py`), mirroring D's:
   - **Preflight:** all D pins, plus D's committed results, plus the A pins.
   - **Phases:**
     - 22 fits (11 per variant), each with full optimiser diagnostics, boundary proximity and FA4 clip counts;
     - FA1–FA4 and F1 evaluation;
     - queue validation through the frozen validator;
     - descriptive and S5 reports;
     - the A-versus-D comparison tables (section 7) read from D's committed results.
6. **Commits:**
   1. the frozen Amendment 4 plus configuration and tests;
   2. the implementation, before any fit;
   3. fit results;
   4. evaluation;
   5. the ledger entry.
7. **Cost estimate.** About 2× D's per-evaluation time (two AR(1) loops), so roughly 10–15 s per evaluation. With up to 300 evaluations × 22 fits on two cores: **about 10–20 hours** of fitting, plus about 1 hour of validation.
