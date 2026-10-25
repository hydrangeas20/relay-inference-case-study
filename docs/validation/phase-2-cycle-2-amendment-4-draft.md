# Cycle 2 Amendment 4: Candidate A procedure (DRAFT, NOT FROZEN)

- **Prepared:** 2026-10-10, for review.
- **Status:** **DRAFT.** Nothing here is frozen.
  - The repository has no record of approval for DA1–DA15, or for the six clarifications of 2026-10-08. So every choice that isn't already fixed by frozen text is marked **[PENDING]**.
  - Once the owner approves (or amends) each item, the approved text goes into the [preregistration](phase-2-cycle-2-preregistration.md) as Amendment 4. It's committed with an executable configuration and freeze tests, before any Candidate A code runs on data.
- **What's not touched:**
  - Candidate D and its ledger;
  - the frozen validator (Amendment 1);
  - the S1, S2–S4, dispersion and rate-range values (Amendments 2–3);
  - all hash-pinned procedure modules.
- **Nothing fitted.** No A code exists; nothing has been fitted, simulated or evaluated. Candidate B hasn't been started. Wednesday and the raw trace weren't accessed.
- **Sources:** the [proposal](phase-2-cycle-2-candidate-a-proposal.md) (`dca9a54`), the [specification audit](phase-2-cycle-2-candidate-a-spec-audit.md) (`034c364`), and the six clarifications of 2026-10-08, reproduced in A4.9.

Key: **[FROZEN]** is already fixed by earlier frozen text. **[PENDING]** needs the owner's decision. **⚠** marks a choice that would alter frozen text.

---

## A4.1 Model (A1, A2)

**[FROZEN, §3]**
- Nₖ ~ Poisson(λₖ·Mₖ·Δ), with Δ = 0.1 s.
- Y = √w·F + √(1−w)·S. F and S are independent unit-variance OU processes, updated exactly per bin: φ = e^(−Δ/τ), F₀ and S₀ ~ N(0, 1).
- M = Q_{σ,ξ}(Φ(Y)), where Q is a mean-1 standardised sinh-arcsinh quantile with SD σ(λ) = a·λ^b, skewness parameter ξ and tail weight δ = 1. Clipped at 0.02.
- A2 replaces ξ with ξ(λ) = c·λ^d.
- Out of range, only σ extrapolates (Q8).

**Executable form** (direct consequences; no new choices):
- Q(Φ(Y)) = 1 + σ(λ)·[sinh(asinh Y + ξ) − μ(ξ)]/s(ξ), because Φ and Φ⁻¹ cancel.
- μ(ξ) = K·sinh ξ.
- s²(ξ) = cosh²ξ + 2·sinh²ξ − K²·sinh²ξ.
- K = 1.3545308064813155.

**Clipping and E[M] = 1 (C1). [PENDING, DA1]**
- Proven (A4.9 Q4): clipping makes E[M] > 1 and SD(M) < σ, strictly, for every σ > 0 and every ξ. So §3's "E[M] = 1" can't hold together with "clipped at 0.02".
- **Proposed (A′):** M = max(M̃, 0.02) with no renormalisation; σ(λ) is defined as the SD **before** clipping.
  - The realised mean, the realised SD and the clip fraction are reported per hour.
  - The resulting intensity inflation λ·(1 + δ) is reported (A4.9 Q5).
- **Alternative (B), ⚠ alters §3:** M = max(M̃, 0.02)/m_c(σ, ξ), which gives exact mean 1.

**A2's coordinates. [PENDING, DA3]**
- ξ = c·(λ̄/λ_ref)^d, with λ̄ = clip(λ, 3.2, 82.82805555555555) and λ_ref = 16.28034943659926 rps.
- This is an exact reparameterisation of c·λ^d: c_frozen = c·λ_ref^(−d). ξ held at λ̄ is Q8's "held at boundary value".

**τ ordering (C2). [PENDING, DA2] ⚠**
- §3 says "τ_f < τ_s" (strict). The proposal's u ∈ [0, 1] includes τ_f = τ_s, and start 8 sat at u = 0.
- **Proposed:** u ∈ [u_min, 1], so τ_s/τ_f ≥ (600/τ_f)^u_min > 1. The value of **u_min is for the owner to set.** Start 8 then moves to u = u_min.
- **Alternative, ⚠ alters §3:** admit τ_f = τ_s as the limiting case.

## A4.2 Parameters and bounds [PENDING, DA2, DA3]

| Coordinate | Bounds | Basis |
|---|---|---|
| log a | [log 0.05, log 5] | Option W (owner-approved for D) |
| b | [−1.0, 0.5] | Option W |
| ξ (A1), or c (A2) | [−2, 2] | δ = 1 skewness saturates at ±1.4405; ±2 reaches ±1.403 |
| d (A2) | [−1, 1] | **Discretionary** |
| w | [0, 1] | Full range; FA1 needs the collapse to be reachable |
| log τ_f | [log 0.1, log 600] | Repository τ grid |
| u | [u_min, 1]; log τ_s = log τ_f + u·(log 600 − log τ_f) | Ordering (C2) |

A1 has 6 parameters, A2 has 7 (§3). [FROZEN]

## A4.3 Starts [PENDING, DA4]

- **Count:** exactly 8 (§4) [FROZEN].
- **Starts 1–7:** rows 1–7 of the Sylvester Hadamard matrix H₈, entry (−1)^popcount(i AND j). Columns 1–6 for A1 and 1–7 for A2, mapped to 0.5 ± 0.3 of each coordinate's range.
- **Start 8:** the Cycle 1 C1 values carried into A:
  - a = 0.4406544452547643, b = −0.32313480634892916;
  - τ_f = 9.23892541130273 s, w = 0.5;
  - u = u_min (C2);
  - ξ = c = ξ_LN(σ_C1(λ_ref)) = 0.33848, with d = 0.
- **The exact values** are written to configuration only after u_min is set.

## A4.4 Optimiser and budget [FROZEN, with one item PENDING]

- **[FROZEN]** The hash-pinned `cycle2_optimizer.fit`, unchanged: Nelder–Mead 1/2/0.5/0.5; initial simplex step 10%; clipping to bounds; FTOL = XTOL = 1e-4; best finite point over all evaluations.
- **[FROZEN]** A budget of **300 evaluations per fit, including the starts** (§4).
- **[PENDING, DA5]** The owner acknowledges the audit's finding (section 3) that most 6–7-dimensional fits will probably stop at the cap.
  - Such fits are **valid** (A3.4).
  - Every falsification outcome is reported with its termination reason.
  - Descriptive misfit in a fit that stopped at the cap isn't attributed to the model family.
  - ⚠ Any budget change would alter §4.

## A4.5 Targets, weights, fits, seeds [PENDING, DA6, DA7, DA15]

**Adopted unchanged for A:**
- A3.1 (tolerances), A3.3, A3.4, A3.5 (targets, weights, fallback, floor), A3.7, A3.8, A3.9 and A3.11;
- D's implementation readings R1–R5;
- A3 addendum 2's optimiser diagnostics.

**Fits:** 11 per variant: `all`, six leave-one-day-out, four `without-band-<b>` (reported only).

**Seeds (C4).** §4 and §6 name numeric seed ranges. As A3.6 did for D, this amendment explicitly adopts hash-derived seeds for A, using `cycle2_seeds.derive_seed` unchanged:

| Stream | Namespace | Indices |
|---|---|---|
| A calibration (shared by A1 and A2) | `relay/cycle2/A/calibration/v1` | (fit, day, hour, replicate 0–2) |
| A validation (shared by A1 and A2) | `relay/cycle2/A/validation/v1` | (held-out day, hour, cell 0–3, replicate 0–19) |
| Poisson control | **reuse** `relay/cycle2/poisson-control/validation/v1` | as for D |

A collision test covers every planned A seed together with every D seed.

## A4.6 Falsification [PENDING, DA8–DA12]

**[FROZEN] wording** (§9, `196074a`): FA1–FA4, F0 and F1, as quoted in the [audit](phase-2-cycle-2-candidate-a-spec-audit.md), section 1.

**FA1, on the full-development fit.** Holds if any of:
- (i) w within 1% of its bound width of 0 or 1;
- (ii) τ_f ≥ 0.8·τ_s;
- (iii) |ξ̂ − ξ_LN| ≤ 0.04, where ξ_LN solves γ(ξ_LN) = σ_ref(σ_ref² + 3), with σ_ref = â·λ_ref^b̂.
  - γ is the δ = 1 skewness (A4.9 Q1). For A2, use ĉ.
  - **Edge cases, [PENDING]:**
    - σ_ref ≥ 0.4498218: no ξ_LN exists, so (iii) doesn't hold;
    - 0.4397 < σ_ref < 0.4498: ξ_LN > 2, so (iii) holds only if ξ_LN ≤ 2.04.
  - Fold fits are reported.

**FA2, on the full-development fit; strict reading.**
- Holds if any S2 component, or any S3 component at W = 10 s, in any band, has |z| > 2, with floored sd_days (§4).
- It's evaluated at the fitted θ; that is the executable form of "can't fit".
- Any aggregate reading ⚠ relaxes §9.

**FA3, on the six fold fits (A4.9 Q2).**
- **Holds if:**
  - max/min of τ_s > 1.5; or
  - max/min of w > 1.5, where a minimum of 0 with a maximum above 0 counts as +∞, and all-zero counts as 1; or
  - τ_s or w is "at a bound" (1% of width) in ≥ 2 folds.
- **For τ_s, "at a bound" means:**
  - u within 0.01 of u_min or 1; or
  - log τ_f within 1% of its upper bound; or
  - log τ_s within 1% of log 0.1.
- **Invalid fold fits:**
  - **[PENDING]** Excluded and recorded; with fewer than 2 valid fits, FA3 is "not evaluable" and doesn't hold.
  - **Stricter alternative:** an invalid fit counts as triggering FA3.

**FA4.**
- Holds if more than 0.1% of all M̃ values are below 0.02, across every bin of every calibration simulation at the full-development fit's best θ.
- Per-hour clip fractions are reported for every fit and every validation run.

**F0 / F1:** as frozen. F1 uses the full-development fit, with every target component at |z| ≤ 2 **and** the frozen rule failing.

**Class aggregation (A4.9 Q3). [PENDING, DA12]**
- §9 attaches the verdict to **class A** ("a class is rejected if any one holds"). It doesn't permit independent final falsification verdicts for A1 and A2.
- Options:
  - **"any"** (conservative): class A is rejected if an FA rule holds for A1's fit or A2's;
  - **"all"**: rejected only if it holds for both.
- Queue validation runs for both variants regardless, and is reported.
- Labels:
  - per variant: PASS / FAIL / INVALID PROCEDURE (operational);
  - for the class: FALSIFIED (FAx) or not falsified.
- ⚠ Per-variant falsification verdicts, or report-only FA rules, would alter §9.

## A4.7 Validation [FROZEN]

- A3.9 and Amendment 1, unchanged. The gating folds go to the frozen `cycle2_validation.validate`.
- The resolution statement applies verbatim.
- Out-of-range bins and the realised-intensity inflation are reported per hour.

## A4.8 Selection [FROZEN §8; mapping PENDING, DA13]

- §8's "passes all three criteria in a fold" means "**the fold passes under Amendment 1**".
- D (3 parameters; 3 of 4) stays the default.
- An A variant is selected over D only if all of these hold:
  - it passes the frozen rule;
  - class A isn't falsified;
  - it passes **4 of 4** gating folds.
- A1 is preferred over A2 on equal fold counts.
- No combined score, and no descriptive criterion.
- **Variants (DA14):** A1 and A2 are both run in full. [PENDING approval]

## A4.9 The six clarifications of 2026-10-08 (findings; for the record)

| # | Question | Finding |
|---|---|---|
| Q1 | FA1's lognormal-equivalent skewness | γ_LN(σ) = σ(σ² + 3).<br>Closed-form δ = 1 skewness, with c = cosh ξ, h = sinh ξ, J = E[Z²√(1+Z²)] = 1.9194216537269737:<br>• μ = hK<br>• E[X²] = c² + 2h²<br>• E[X³] = 3c²hJ + h³(K + J)<br>• γ = (E[X³] − 3μ·E[X²] + 2μ³)/s³<br>γ is odd and increasing, with supremum 1.4404821. λ_ref = 16.28034943659926 rps |
| Q2 | FA3's quantities | τ_s (always ≥ 0.1 s, so positive) and w (can be exactly 0). Handling of zeros and invalid fold fits as in A4.6 |
| Q3 | §9 whole-class rule | Verdicts attach to the class (FB1 shows the authors named variants where they meant to). Whether "any" or "all" variants decide is undetermined: owner decision |
| Q4 | Does clipping reduce variance across the whole domain? | Yes, strictly, for all σ > 0 and ξ ∈ ℝ. Var f(X) = ½E[(f(X) − f(X′))²], and max(·, c) is 1-Lipschitz, with strict contraction on {X < c}. P(X < c) > 0 because the support is ℝ. Likewise E[M] > 1 |
| Q5 | Intensity under clipping | E[Nₖ] = λₖ·Δ·(1 + δₖ), with δₖ > 0, largest at low λ (b < 0) and ξ < 0.<br>• **Calibration is blind to it:** S1–S4 are normalised by the simulated hour's own trend; S1 sees only the realised CV σ·r/(1+δ).<br>• **The queue test isn't:** c = ⌈λ_ref·s/ρ⌉ uses Azure's rate, so utilisation becomes ρ(1 + δ̄). Negligible inside FA4's regime (δ̄ ≤ about 10⁻⁴); about 1.7% at σ = 0.5, ξ = −1 |
| Q6 | Conflicts with frozen text | C1: E[M] = 1 versus the clip. C2: τ_f < τ_s versus u = 0. C3: A2's reparameterisation, not a conflict. C4: seed ranges versus hash seeds |

## A4.10 Owner decisions needed to freeze

1. **DA1 / C1:** clipping, (A′) or (B).
2. **DA2 / C2:** the value of u_min, or an amendment admitting τ_f = τ_s.
3. **DA3:** the bounds, including the discretionary d ∈ [−1, 1].
4. **DA4:** the starts design; the exact values follow from u_min.
5. **DA5:** acknowledgement of the budget's interpretation.
6. **DA6 / C4 and DA15:** hash seeds, shared namespaces, Poisson reuse; adopting A3 for A.
7. **DA7 and DA14:** 11 fits per variant; both variants run.
8. **DA8–DA11:** the FA1–FA4 executable definitions, including FA1's edge cases and FA3's invalid-fold handling.
9. **DA12:** class aggregation, "any" or "all".
10. **DA13:** the §8 mapping.
