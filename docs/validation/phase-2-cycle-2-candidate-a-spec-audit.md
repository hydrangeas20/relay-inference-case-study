# Phase 2, Cycle 2: Candidate A specification audit (PROPOSAL ONLY)

- **Prepared:** 2026-10-08, at the owner's request, before Amendment 4.
- **Status:** an audit of the [Candidate A proposal](phase-2-cycle-2-candidate-a-proposal.md) (`dca9a54`). **Nothing here is approved or frozen.**
- **Candidate-independent.** Every number below is analytical, or comes from synthetic distributions and synthetic objective functions.
  - No Azure data was read.
  - No Candidate A model was built, fitted, calibrated or simulated.
  - No traffic or queue was generated.
  - Candidate B hasn't been started.
  - Wednesday and the raw trace weren't accessed.
- **Reproduce:** `uv run python analysis/cycle2_a_spec_audit.py`. It's deterministic, and writes `analysis/results/cycle2/a-spec-audit.json`.

---

## 1. The original rules: frozen wording, direct implications, and the choices still needed

**Source.**
- File: `docs/validation/phase-2-cycle-2-preregistration.md`, §8 (lines 163–168) and §9 (lines 170–188).
- Originating commit: `196074ab6302e3705bd64cdc14b7a6bf53698630` (hydrangeas20, 2026-10-02), "Cycle 2 preregistration: pre-candidate skeleton".
- `git log -L163,188` shows no later commit touching these lines. The wording below is exactly as frozen before any candidate existed.

**§9 heading (frozen):** "Falsification rules (a class is rejected if any one holds)". Then: "All classes: (F0) It fails the internal pass rule. (F1) It fits its in-sample targets within 2 × sd_days but still fails the queue test."

**How sd_days is defined (§4, same commit):** "the standard deviation (ddof = 1) across development days of that day's band-pooled value, over days with ≥ 3 eligible hours in the band. It is floored at 0.25 × the median of that statistic's sd_days across bands." So within this preregistration, **sd_days includes the floor.**

| Rule | Frozen wording (verbatim) | Directly implied by the wording | New discretionary choice needed to make it executable |
|---|---|---|---|
| **FA1** | "The fit collapses to Cycle 1's structure: w at 0 or 1, τ_f within 20% of τ_s, or ξ at the skew of the lognormal equivalent." | A **disjunction**: any one of the three conditions triggers it. "τ_f within 20% of τ_s" means \|τ_s − τ_f\| ≤ 0.2·τ_s, so τ_f ≥ 0.8·τ_s (τ_s is the reference). "w at 0 or 1" needs bounds that include 0 and 1 | (a) **Which fit**: "the fit" isn't named. (b) What counts as being "at" 0 or 1: exact equality is almost never reached numerically. (c) "The lognormal equivalent": the lognormal skewness σ(σ² + 3) depends on σ(λ), so a reference rate is needed; for A2, ξ also varies with λ. (d) The tolerance for "at the skew" |
| **FA2** | "It can't fit S3 (10 s) and S2 within 2 × sd_days at the same time, in-sample." | The S3 components at W = 10 s (7 per band) and the S2 components (7 per band). Each must have \|ŝ − s_obs\| ≤ 2·sd_days, with floored sd_days (§4), **simultaneously at one θ**, on the fitted data | (a) "Can't fit" is literally a statement about every θ, which can't be established. The executable reading evaluates the **fitted** point; that's an interpretation. (b) Which in-sample fit: the full-development fit, or each fold's fit, where the fallback sd applies. (c) Whether "within" means every component in every band (implied by the plain wording) or an aggregate (a new choice, and a relaxation) |
| **FA3** | "τ_s or w varies by more than 50% across the leave-one-day-out folds, or sits at a bound in more than one fold." | The six leave-one-day-out fits. Two triggers: variation > 50% in τ_s **or** in w; or τ_s or w at a bound in ≥ 2 of the 6 folds. Needs bounds on τ_s and w | (a) The **variation metric** for "varies by more than 50%": max/min > 1.5, (max − min)/median > 0.5, or deviation from the full fit. None is implied. (b) The proximity tolerance for "at a bound" |
| **FA4** | "More than 0.1% of M samples are clipped." | The fraction of multiplier values Mₖ hit by the 0.02 floor is > 0.001. Mₖ is per 0.1 s bin | (a) **The population**: which fit, which simulations (calibration or validation), aggregated or per hour |
| F0 | "It fails the internal pass rule." | Under Amendment 1 (A1.2 item 7: binding for D1, A1, A2, B2, B3), the internal pass rule **is** the frozen validator's rule | None |
| F1 | "It fits its in-sample targets within 2 × sd_days but still fails the queue test." | Every in-sample S1–S4 target component has \|z\| ≤ 2, using floored sd_days, **and** the frozen rule fails | Which in-sample fit (as FA2 b) |
| §9 scope | "a class is rejected if any one holds" | Rejection applies to the **class** | **A has two variants.** Rejecting the class because of one variant's fit (strict) and evaluating each variant separately (lenient) are both readings. The lenient one could **relax** the frozen rule |

**§8 (frozen; lines 165–168):**

> - **Who's eligible:** candidates passing the internal rule under identical frozen criteria.
> - **Default:** the one with the **fewest effective parameters** (section 3).
> - **Exception:** a more complex candidate is chosen only if it shows a **materially meaningful validation advantage**, defined as passing all three criteria in **more gating folds** than the simpler one (for example 4 of 4 against 3 of 4). The highest criterion-1 fraction is **not** a selection criterion.
> - **Comparator C** is never eligible.

- **Directly implied:**
  - eligibility = passing the internal rule;
  - the default is the eligible candidate with the fewest parameters;
  - a more complex candidate replaces it only with a **strictly greater** count of passing gating folds. The worked example is exactly 4 of 4 against 3 of 4.
  - A class rejected under §9 can't be selected: rejection excludes it.
- **Choice still needed:** "passing all three criteria" refers to Cycle 1's per-cell criteria 1–3. Amendment 1 superseded criteria 1 and 2 and redefined a fold pass. So the referent has to be mapped (section 5).

---

## 2. The proposed marginal link

### 2.1 The transformation is correct as written

The variate is X = sinh(asinh Z + ξ), with Z ~ N(0, 1). This is the Jones–Pewsey sinh-arcsinh variate with δ = 1.

- **Monotone in Z.** So with Y ~ N(0, 1), the Gaussian-copula quantile Q(Φ(Y)) = sinh(asinh Y + ξ) exactly: Φ cancels.
- **Gaussian-weight tails.** As Y → +∞, X ≈ e^ξ·Y; as Y → −∞, X ≈ e^(−ξ)·Y. Both tails are linear in a Gaussian, with different scales on each side. That's the "tail weight fixed at Gaussian" in §3, and it's lighter than the lognormal's right tail.
- **Closed forms confirmed** against numerical integration to ≤ 5·10⁻¹⁶ for ξ ∈ {0, ±0.5, ±1, ±2}:
  - μ(ξ) = K·sinh ξ;
  - s²(ξ) = cosh²ξ + 2·sinh²ξ − K²·sinh²ξ;
  - K = E√(1 + Z²) = 1.3545308064813155.
- **Skewness of X:** 0, ±0.754, ±1.170 and ±1.403 at ξ = 0, ±0.5, ±1 and ±2. It saturates near ±1.44.
- **Before clipping,** M̃ = 1 + σ(X − μ)/s has mean 1 and SD σ exactly. This is confirmed by 2·10⁷-draw Monte Carlo within sampling error.

### 2.2 Clipping at 0.02 breaks exact mean and SD preservation

**Analytical result.** For every σ > 0 and every ξ, the support of M̃ is the whole real line, so P(M̃ < 0.02) > 0. With M = max(M̃, 0.02):
- **The mean rises:** E[M] = 1 + E[(0.02 − M̃)⁺] > 1, strictly.
- **The variance falls:** Var(M) < Var(M̃) = σ². Clipping is a 1-Lipschitz map that isn't an isometry on a set of positive probability.

So the frozen §3 generator property "E[M] = 1" and the frozen A1 text "clipped at 0.02" **can't both hold exactly.** This is a tension inside the frozen text. This audit doesn't resolve it.

**Magnitude** (exact 1-D quadrature; cross-checked with Monte Carlo). Each cell shows E[M] − 1 / SD(M)/σ / P(clip):

| σ | ξ = −2 | ξ = −1 | ξ = 0 | ξ = +1 | ξ = +2 |
|---|---|---|---|---|---|
| 0.1 | ~0 / 1.000 / 1e-9 | ~0 / 1.000 / 9e-11 | 0 / 1.000 / 0 | 0 / 1.000 / 0 | 0 / 1.000 / 0 |
| 0.2 | 5.1e-5 / 0.9986 / 5.4e-4 | 2.5e-5 / 0.9993 / 3.0e-4 | 1.8e-8 / 1.0000 / 4.8e-7 | 0 / 1.000 / 0 | 0 / 1.000 / 0 |
| 0.3 | 1.7e-3 / 0.978 / 9.4e-3 | 1.2e-3 / 0.985 / 7.3e-3 | 4.3e-5 / 0.9995 / 5.4e-4 | ~0 / 1.000 / 0 | 0 / 1.000 / 0 |
| 0.5 | 2.0e-2 / 0.886 / 5.5e-2 | 1.7e-2 / 0.905 / 5.2e-2 | 4.7e-3 / 0.978 / 2.5e-2 | 4.6e-8 / 1.000 / 1.9e-6 | 0 / 1.000 / 0 |
| 1.0 | 0.139 / 0.704 / 0.159 | 0.132 / 0.733 / 0.162 | 0.087 / 0.863 / 0.164 | 0.021 / 0.976 / 0.123 | 5.2e-3 / 0.995 / 0.077 |
| 2.0 | 0.476 / 0.563 / 0.251 | 0.467 / 0.595 / 0.261 | 0.402 / 0.741 / 0.312 | 0.296 / 0.869 / 0.394 | 0.266 / 0.893 / 0.419 |

**Rate dependence.** With σ(λ) = a·λ^b, the realised multiplier has:
- mean 1 + δ(σ(λ), ξ), so the realised rate is λ·(1 + δ);
- SD σ(λ)·r(σ(λ), ξ), with r < 1.

So **neither the realised mean nor the realised SD follows the stated power law where clipping occurs.** When b < 0, σ is largest at low λ, so the distortion concentrates in **low-rate hours**, and grows when ξ < 0 (a left-skewed marginal puts mass towards 0).

- **Cycle 1 C1 scale (pre-Cycle-2 history), for reference:** σ ≈ 0.30 at 3.2 rps. At ξ = 0 the distortion there is negligible (mean +4·10⁻⁵, SD −0.05%). At ξ = −1 it's +0.12% and −1.5%.
- **The Option W box allows much larger σ,** where the distortion is material, for ξ ≤ 0: up to 2% in the mean and 11% in the SD at σ = 0.5, and up to 14% and 30% at σ = 1.

**Relation to FA4.** At a single-bin clip probability of exactly 0.1% (FA4's threshold), the mean shift is ≤ 1.1·10⁻⁴ and SD(M)/σ ≥ 0.9975 at every tested ξ (0, ±0.5, ±1, ±2). That threshold sits at σ ≈ 0.21 (ξ = −2) up to σ ≈ 0.83 (ξ = +2).

So **a fit that doesn't trigger FA4 has negligible average distortion. But FA4 is an aggregate:** a fit can stay below 0.1% overall while clipping much more often in its low-rate hours.

### 2.3 The copula doesn't fully separate dependence from marginal shape

For ξ ≠ 0, the transform is nonlinear. So corr(Mₜ, Mₜ₊ₗ) = g_ξ(ρ_Y(l)) < ρ_Y(l), where ρ_Y = w·e^(−l/τ_f) + (1−w)·e^(−l/τ_s). Unclipped, by Hermite expansion:

| ξ | Hermite rank-1 share | ρ_Y = 0.1 | 0.3 | 0.5 | 0.8 | 0.95 |
|---|---|---|---|---|---|---|
| 0 | 1.000 | 0.100 | 0.300 | 0.500 | 0.800 | 0.950 |
| 0.5 | 0.966 | 0.097 | 0.293 | 0.491 | 0.794 | 0.948 |
| 1 | 0.913 | 0.092 | 0.281 | 0.478 | 0.785 | 0.946 |
| 2 | 0.867 | 0.088 | 0.272 | 0.466 | 0.778 | 0.943 |

The skew parameter attenuates the multiplier's autocorrelation by up to about 12% at small correlations (ρ_Y = 0.1, ξ = 2), and about 7% at ρ_Y = 0.5. So "independent control" of dependence (w, τ_f, τ_s) and marginal (ξ) is **approximate**. It's exact only at ξ = 0. This doesn't change the model; it's a property to state when interpreting fitted values.

### 2.4 Alternatives for the clipping tension (none selected)

| Option | Realised mean | Realised SD | Changes the specified family? | Conflict with frozen text | Trade-off |
|---|---|---|---|---|---|
| **(A) Literal:** clip, no renormalisation | > 1 where clipping occurs | < σ(λ) | No | Keeps "clipped at 0.02". Violates "E[M] = 1" by the amounts above | Simplest; bias small inside FA4's regime. Needs per-hour reporting of realised mean and SD, and of the clip fraction |
| **(A′) As (A),** with σ(λ) defined explicitly as the **pre-clip** SD | as (A) | as (A) | No | Same as (A); only the meaning of σ is made exact | Honest labelling; no computational change. Still violates E[M] = 1 |
| **(B) Clip, then renormalise the mean:** M = max(M̃, 0.02)/m_c(σ, ξ), with m_c the exact clipped mean (1-D integral, or closed form via partial moments, per bin) | exactly 1 | SD_c/m_c ≠ σ (lower) | Minor: same clipped SHASH shape, rescaled per (σ, ξ). The floor becomes 0.02/m_c | Restores §3's E[M] = 1; adds a step that "clipped at 0.02" doesn't state | Small extra computation. σ's meaning drifts at large σ |
| **(C) Two-moment matching:** choose (σ′, shift) per (σ, ξ) so the clipped variable has mean 1 and SD σ | 1 | σ | Same shapes, different parameter map | Adds machinery not in §3 | Exact moments where feasible; **infeasible or unstable at large σ**; a lookup table and root-finding per bin; harder to audit |
| **(D) A smooth positive link** instead of clipping (for example a softplus) | 1, by construction | depends | **Yes:** not the Gaussian-copula SHASH family in §3 | Replaces frozen structure | Outside the authorised specification. Listed for completeness only |
| **(E) Treat heavy clipping as an invalid evaluation** (+∞ above some clip fraction) | as (A) | as (A) | No | **Changes FA4's role:** a constraint replaces a falsification rule, so FA4 could never fire at the best point | Would alter frozen falsification semantics. Not recommended without an explicit amendment |

---

## 3. Optimiser feasibility (prospective; budget unchanged; no A optimisation)

**Budget arithmetic under the frozen procedure** (A3.3, `cycle2_optimizer`):
- 300 evaluations, minus 8 starts, minus n initial-simplex vertices: **286 (A1, n = 6) or 285 (A2, n = 7)** evaluations remain for Nelder–Mead iterations.
- A typical iteration costs 1–2 evaluations; a shrink costs n.
- Convergence requires **both** an objective spread ≤ 1e-4 (absolute, on a loss of order 10²–10³) **and** a coordinate spread ≤ 1e-4, in coordinate units.

**Synthetic benchmark.** The frozen `fit`, unchanged, on synthetic objectives only, in the unit box:
- scaled like D's loss: minimum 700, values of about 10⁴ across the box;
- 8 starts: Hadamard rows plus one interior point;
- 20 replicates per case;
- excess = best objective − 700.

| Objective | n | Converged within 300 | Median evaluations if converged | Median excess | Max excess |
|---|---|---|---|---|---|
| Sphere | 3 | 100% | 102 | 5e-5 | 2e-4 |
| Sphere | 6 | 90% | 253 | 5e-5 | 9e-4 |
| Sphere | 7 | 10% | 293 | 2e-3 | 0.04 |
| Rotated quadratic, condition 1e2 | 3 | 100% | 123 | 2e-5 | 2e-4 |
| Rotated quadratic, condition 1e2 | 6 | 20% | 289 | 9e-4 | 5.3 |
| Rotated quadratic, condition 1e2 | 7 | **0%** | — | 2.1 | 867 |
| Rotated quadratic, condition 1e4 | 3 | 100% | 157 | 2e-6 | 103 (one premature stop) |
| Rotated quadratic, condition 1e4 | 6 | **0%** | — | 14 | 470 |
| Rotated quadratic, condition 1e4 | 7 | **0%** | — | 59 | 2828 |
| Banana valley | 3 | 100% | 201 | 3e-6 | 1e-5 |
| Banana valley | 6 | **0%** | — | 0.07 | 26 |
| Banana valley | 7 | **0%** | — | 0.17 | 20 |

**Check against D (procedural only).** The 3-D medians (102–201) bracket D's actual 128–168 evaluations. So the benchmark's scaling is consistent with the real loss.

**Expected limitations for A:**
- **Most A fits will stop at the cap,** not by convergence.
  - In 6–7 dimensions the frozen tolerances are rarely met within 285–286 Nelder–Mead evaluations, even on easy objectives.
  - The memo expects the timescales to be "weakly identified" (an ill-conditioned or curved valley). On objectives like that, the best point at the cap can be **materially suboptimal**: excess of order 10–10³ on a loss whose minimum is 700.
- **The search is local.** Nelder–Mead from one start can also stop prematurely; that happened in one 3-D case, condition 1e4.
- **The procedures are asymmetric.** D (3 parameters) converged in every fit, while A probably won't. Equal budgets aren't equal optimisation quality.

**The exact frozen interpretation** (A3.3, A3.4; unchanged unless amended):
- The result is the **best finite point among all evaluations.** The termination reason (`converged` or `budget_exhausted`) is recorded.
- **A fit at the cap is VALID.** A fit is invalid only if all 8 starts are +∞, its best objective is non-finite, or its parameters lie outside the bounds. Reaching the cap is neither a failure nor a reason to restart: no restarts, perturbations or second runs (A3.4, A3.11).
- **Consequence for interpretation.** A budget-exhausted A fit's descriptive misfit **can't** be attributed to the model family. FA1–FA3, evaluated at non-converged points, could trigger because of the optimiser rather than the structure:
  - FA1, from a w or u stuck near a start or a bound;
  - FA2, from a suboptimal θ;
  - FA3, from fold-to-fold optimiser scatter.

  A3 addendum 2's diagnostics (termination, evaluations, start objectives, invalid evaluations, boundary proximity) were written for D. Proposal: adopt them for A, with every falsification outcome reported **alongside its termination reason**. The falsification outcome itself stands as frozen.

The budget isn't changed here. Any change would alter §4's frozen "at most 300 loss evaluations per fit" and would need a dated amendment. This benchmark is a candidate-independent basis the owner could cite, but this audit doesn't propose one.

---

## 4. Decision table (DA1–DA15)

Key: **S** = model structure, **C** = calibration, **F** = falsification, **V** = validation, **Sel** = selection. "Without A results?" asks whether it can be resolved without inspecting any Candidate A result.

| ID | Proposed choice (proposal `dca9a54`) | Already constrained by the preregistration? | Affects | Without A results? | Recommendation and rationale |
|---|---|---|---|---|---|
| DA1 | Clip at 0.02, no renormalisation | **Yes, and in tension:** §3 "clipped at 0.02" and "E[M] = 1" (section 2.2) | S, C, F (FA4) | Yes | **(A′):** the literal clip, with σ defined as the pre-clip SD, and per-hour reporting of realised mean, SD and clip fraction. It's the only option that doesn't add structure to frozen text. Choose (B) only by explicit amendment if exact E[M] = 1 matters more |
| DA2 | (log τ_f, u), so τ_f ≤ τ_s ≤ 600 s | Partly: §3 requires τ_f < τ_s | S (domain), C, F (FA1 reachability) | Yes | **As proposed.** It enforces the ordering everywhere and keeps FA1's "τ_f within 20% of τ_s" reachable. The alternative builds the memo's unfrozen 1–3 s / 20–60 s idea into the bounds |
| DA3 | Option W (a, b); ξ, c ∈ [−2, 2]; d ∈ [−1, 1]; w ∈ [0, 1]; τ grid | No (Option W was approved for D only) | C, F (FA3 "at a bound"), S (domain) | Yes | **As proposed** for a, b, ξ, w and τ: each has a stated basis (owner approval, SHASH saturation, the full w range, the repository τ grid). **d ∈ [−1, 1] is discretionary**: the owner's call |
| DA4 | Hadamard H₈ rows 1–7 at 0.5 ± 0.3, plus the Cycle 1 C1 start | Partly: §4 freezes the **count** (8) | C | Yes | **As proposed.** Balanced (each level 3–4 times), nearly orthogonal, deterministic, and mirrors A3.2's 7 + historical start. No D result used |
| DA5 | 300 per fit, starts included | **Yes:** §4 "at most 300 loss evaluations per fit" | C, and the interpretation of F | Yes | **Keep 300 (frozen).** Adopt the termination-aware reporting in section 3. ⚠ **Any increase would alter a frozen rule.** Not proposed |
| DA6 | Shared A1/A2 namespaces; reuse the Poisson-control namespace | No (A3.6 is D-specific) | C, V | Yes | **As proposed.** Paired comparisons (A1 vs A2 by common random numbers; an identical Poisson control and Azure for A vs D); D's Poisson medians reproduced as a check |
| DA7 | 11 fits per variant, as D | Partly: §6 freezes leave-one-day-out, and lists band holdouts "10–30 and 30–60, as in Cycle 1" (reported) | C, V (reported) | Yes | **As proposed.** It's a superset of §6's two holdouts, reported only, and matches D's set for comparability. Doesn't relax anything |
| DA8 | FA1: w within 1% of bound width; τ_f ≥ 0.8·τ_s; skewness within ±0.05 of the lognormal skewness at λ_ref; full-development fit | **Yes, wording frozen** (section 1) | F | Yes | (i) **w at a bound:** within 1% of the bound width (reuses D's R5 convention). (ii) **τ_f ≥ 0.8·τ_s:** directly implied. (iii) Replace the proposal's ±0.05 (no basis) with \|ξ − ξ_LN(σ̂(λ_ref))\| ≤ 1% of ξ's bound width (= 0.04). That reuses the same proximity convention, so **no new tolerance concept**. For A2, use c at λ_ref. **Which fit:** the full-development fit (the literal "the fit"); fold fits reported |
| DA9 | FA2: any S2 or S3(10 s) \|z\| > 2, floored sd, full-development fit | **Yes** (section 1) | F | Yes | **Keep the strict implied reading:** every component, every band, with floored sd_days as §4 defines. Any aggregate reading **relaxes** the frozen rule. Evaluate at the fitted θ of the full-development fit, and state that this is the executable form of "can't fit" |
| DA10 | FA3: (max − min)/median > 0.5 | **Yes, wording frozen**; the metric isn't | F | Yes | **max/min > 1.5** across the six fold fits: the plainest reading of "varies by more than 50%". "At a bound": within 1% of bound width (R5), in ≥ 2 folds. Unstable as w → 0, but FA1 already covers that region |
| DA11 | FA4: all bins of all calibration simulations at the full-development fit's best θ | **Yes** (threshold); the population isn't | F | Yes | **As proposed,** and additionally report per-hour clip fractions for every fit and every validation simulation (section 2.2's aggregation caveat) |
| DA12 | FA rules gate per variant; queue validation still run; labels PASS / FAIL / FALSIFIED / INVALID PROCEDURE | **Yes:** §9 "a class is rejected if any one holds" | F, Sel | Yes | Keep the FA rules **gating**, and run and report queue validation regardless (adds information; relaxes nothing). ⚠ **Per-variant evaluation could relax the class-level wording:** an A2 that passes would survive an A1 falsification. Owner decision. The strict literal reading: class A is rejected if any FA rule holds for any variant. ⚠ The "report-only" alternative **would retrospectively relax §9** and isn't recommended |
| DA13 | "Passes all three criteria" maps to "the fold passes under Amendment 1" | **Yes:** the §8 referent was superseded by Amendment 1 (A1.2 item 7) | Sel | Yes | **As proposed** (section 5). It's the only fold-level pass that remains, and it reproduces §8's own example |
| DA14 | Run A1 and A2 in full | **Yes:** §3 names both within the five-variant cap | C, V, Sel | Yes | **As proposed.** No results-dependent sequencing |
| DA15 | Adopt A3.1, 3.3, 3.4, 3.5, 3.7, 3.8, 3.9 and 3.11 for A, plus D's R1–R5 | No (A3 is D-specific) | C, V, F | Yes | **As proposed, plus A3 addendum 2's diagnostics** (section 3), so A gets the same procedure and interpretation rules as D |

**⚠ Decisions that could retrospectively alter a frozen rule:**
- DA5, any budget change (§4);
- DA9, any non-strict FA2 reading (§9);
- DA12, the per-variant or report-only readings (§9);
- DA1 options (B), (C), (D) and (E): (B) and (C) add structure to §3's link; (D) replaces it; (E) changes FA4's role.

All 15 can be resolved **before** any Candidate A result exists.

---

## 5. Selection integrity

**Does §8 require A to pass four gating folds to replace D? Yes.**
- §8's exception requires the more complex candidate to pass in **more gating folds than the simpler one**, with the example "4 of 4 against 3 of 4".
- D passed 3 of 4. So an A variant needs **4 of 4**, under the only available mapping of "passes all three criteria" to "the fold passes under Amendment 1" (C1′, the near-zero cap and criterion 3).
- Without that mapping, §8's text points to criteria that Amendment 1 removed and can't be evaluated. Amendment 1 binds every candidate's internal validation to the frozen rule (A1.2 item 7).

**Three separate statuses, never combined:**

| Status | Defined by | D (recorded) | What it decides |
|---|---|---|---|
| **Operational PASS / FAIL** | The frozen validator: ≥ 3 of 4 gating folds pass, and no C2′ safety violation | PASS (Mon, Tue, Thu; Fri failed) | F0 |
| **Falsification** | §9: F0, F1 and the class rules (FA1–FA4 for A; FD1 superseded for D by A3.4) | Not falsified: F0 doesn't hold (it passed); F1 doesn't hold (it didn't fit in-sample within 2·sd_days); FD1 doesn't apply | Eligibility: a rejected class can't be selected |
| **Selection** | §8 among eligible candidates: fewest parameters by default; more complex only with strictly more passing gating folds | Provisional default (3 parameters) | Which candidate goes forward |

**Consequences, all directly implied by the frozen text:**
- **A doesn't replace D** if it:
  - passes 3 of 4, however much better its descriptive fit;
  - passes 4 of 4 but is falsified;
  - passes 4 of 4 with a safety violation, since that fails the rule.
- **An A variant replaces D only if** it passes the rule with 4 of 4 gating folds and isn't falsified.
- **Between A1 and A2,** the same rule applies, with A1 as the simpler.
- **Descriptive metrics** (S1–S4 residuals, tolerances, S5), the size of G, and criterion-3 fractions never enter selection.
- **No combined score and no new threshold** is defined.
- **When selection becomes final** isn't stated in §8. With Candidate B not run, it remains the owner's decision.

---

## 6. Decisions requiring the owner's explicit approval before Amendment 4

1. **DA1:** how to resolve the clip / E[M] = 1 tension: (A′) literal with σ as the pre-clip SD (recommended), or (B) mean renormalisation by amendment.
2. **DA12:** whether FA1–FA4 apply to class A as a whole (strict, literal) or per variant (could relax §9). And confirmation that queue validation runs regardless, for reporting.
3. **DA8 (iii) and DA10:** the executable tolerances. ξ within 1% of its bound width of ξ_LN at λ_ref; max/min > 1.5 for FA3's "varies by more than 50%".
4. **DA9:** confirmation of the strict FA2 reading. It's implied by the wording, but it may well falsify A.
5. **DA5:** acknowledgement that 300 evaluations will probably end most A fits at the cap, with the termination-aware interpretation in section 3. Any change would alter §4.
6. **DA3:** the discretionary range d ∈ [−1, 1].
7. **DA13:** confirmation of the §8 mapping.
8. **DA2, DA4, DA6, DA7, DA11, DA14, DA15:** approval as proposed, or amendment.
