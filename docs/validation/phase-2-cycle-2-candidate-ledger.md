# Phase 2, Cycle 2: candidate ledger

One entry per candidate run under the frozen Cycle 2 procedure ([preregistration](phase-2-cycle-2-preregistration.md), Amendments 1–3 and addenda). Entries are append-only. A result is never edited after it's recorded; corrections are new, dated entries.

| Candidate | Authorised | Verdict | Wednesday |
|---|---|---|---|
| D (variant D1) | 2026-10-08 | **PASS** (internal; 3 of 4 gating folds, no safety violation) | Closed. Not accessed |
| A (A1, A2) | Not authorised | — | — |
| B (B2, B3) | Not authorised | — | — |

---

## Candidate D (D1): single-timescale lognormal OU, Cycle 1 family

- **Authorised by:** hydrangeas20, 2026-10-08, for Candidate D only. It asks whether the original single-timescale lognormal OU family can reproduce the richer Cycle 2 statistics and queue behaviour without extra structure.
- **Run once,** under the frozen procedure. No rescue, rerun or variant (A3.11).

### D.1 Identity and provenance

| Item | Value |
|---|---|
| Start commit | `04cd5bd` (all of Amendment 3 frozen) |
| Implementation commit | `8d1805a` (committed before any fit) |
| Fit results commit | `68e008a` (fits run at `8d1805a`, clean tree) |
| Evaluation results commit | `dbc25ea` (evaluation run at `68e008a`, clean tree) |
| Code | `analysis/cycle2_candidate_d.py` |
| Results | `analysis/results/cycle2/candidate-d/` (`fit-run.json`, `fit-<id>.json` × 11, `evaluation.json`) |
| Generator | the shipped `relay.traffic.generate.cox_arrivals` and `relay.traffic.burstiness.BurstinessModel`, unchanged |
| Data | the six development days only, from `training.npz` `1f0e15da…b92362` and `validation.npz` `47ea7ddf…a4fde7` (manifest-verified), under the cache-only guard |

**Preflight.** It runs at the start of both the fit and the evaluation, and fails closed. Both runs passed:
- **15 pinned hashes** match their recorded identities:
  - the frozen validator and the freeze record's implementation, audit code and audit results;
  - `cycle2_optimizer.py`, `cycle2_seeds.py` and `cycle2_targets.py`;
  - the S1 tolerance result and the Amendment 3 dispersion result.
- **Validator constants** match Amendment 1 (B = 1.40, safety 0.5–2.0, cap 0.10, 3 folds).
- **The eight starts** equal `D_STARTS_THETA`.
- **Both caches** match the manifest.
- **The Azure S1–S4 components** recomputed by the runner reproduce the frozen full-development dispersion and rate range exactly.
- **Only the six development days** were loaded. Wednesday (`2024-05-15`) isn't in any input or path.

The raw trace was never opened. Its last-access time is still 2026-09-28 16:09.

**Implementation readings,** fixed in the module docstring at `8d1805a`, before any D result:

| Reading | What it fixes |
|---|---|
| R1 | The simulated band-pooled value pools all of a band's simulated hour-replicates (hours × 3 seeds), with the data's pooling rule |
| R2 | The held-out descriptive comparison uses calibration-namespace seeds with fit id = the held-out day. The fold's own fit never used these |
| R3 | Band-holdout scoring: band b's hours (six days), simulated with the `without-band-b` fit and its seeds. Scored as the max over windows of the absolute S1 error, against the frozen S1 tolerance |
| R4 | An invalid fold fit is a failing fold with no safety violation. It didn't arise |
| R5 | "Near a bound" means within 1% of the bound width |

### D.2 Fits and optimiser behaviour

All fits use the Option W bounds, the eight frozen starts, the 300-evaluation budget, Nelder–Mead from the best start, and the frozen loss and weights. "Distance to bound" is the minimum over coordinates, as a fraction of the bound width.

| Fit | a | b | τ (s) | Best L | Evaluations | Invalid | Chosen start (L; best other start) | Fallbacks | Distance to bound |
|---|---|---|---|---|---|---|---|---|---|
| all | 0.4923 | −0.3550 | 7.87 | 714.4 | 130 | 1 | 8 (848; 8369) | 0 | 0.430 |
| held out Fri | 0.4656 | −0.3426 | 8.59 | 976.8 | 138 | 1 | 8 (1091; 11191) | 0 | 0.438 |
| held out Sat | 0.4143 | −0.3273 | 8.70 | 668.0 | 149 | 1 | 8 (865; 8364) | 0 | 0.448 |
| held out Sun | 0.3772 | −0.3005 | 9.21 | 618.8 | 134 | 1 | 8 (882; 8321) | 0 | 0.439 |
| held out Mon | 0.3849 | −0.3065 | 10.67 | 643.9 | 128 | 1 | 8 (915; 7783) | 30 | 0.443 |
| held out Tue | 0.4320 | −0.3304 | 8.11 | 693.6 | 168 | 1 | 8 (1109; 9133) | 30 | 0.446 |
| held out Thu | 0.3879 | −0.3208 | 10.77 | 902.1 | 153 | 1 | 8 (1311; 9367) | 30 | 0.445 |
| without 3–10 | 0.4890 | −0.3686 | 9.17 | 564.4 | 140 | 0 | 8 (715; 8387) | 0 | 0.421 |
| without 10–30 | 0.3805 | −0.3068 | 9.92 | 536.2 | 144 | 1 | 8 (884; 7766) | 0 | 0.441 |
| without 30–60 | 0.4463 | −0.3445 | 8.29 | 474.4 | 135 | 1 | 8 (884; 5948) | 0 | 0.437 |
| without 60–120 | 0.3856 | −0.2871 | 8.89 | 286.2 | 130 | 1 | 8 (353; 2309) | 0 | 0.444 |

- **Every fit is valid and converged** under the frozen tolerances, using 128–168 of the 300 evaluations. None hit the cap.
- **Start 8 (Cycle 1 C1) was the lowest start in every fit,** about 6.5–12× below the best of starts 1–7.
- **No best point lies near a bound.** The nearest coordinate is at least 42% of the width from its bound.
- **The one invalid evaluation per fit** is start 3 (a ≈ 3.16): the statistics are non-finite, so it's counted as +∞. That's the frozen rule.
- **Determinism:** each fit's best objective was recomputed independently and matched exactly (common random numbers).
- **Fallbacks:** exactly those expected — 60–120 rps, all 30 components, in the Mon, Tue and Thu folds (A3.5).
- **The leave-one-day-out parameters are stable:** a 0.38–0.47, b −0.30 to −0.34, τ 8.1–10.8 s. They lie close to Cycle 1 C1 (0.441, −0.323, 9.24 s).
- **Out-of-range bins** (A3.8; only σ extrapolates): 16 of the 143 development hours have some 0.1 s bins outside 3.2–82.83 rps, at most 63% of an hour. Per-hour fractions are in `fit-run.json`. They're the same for every evaluation, because each hour's trend is fixed data. In the validation folds:
  - Fri: none
  - Sat: hours 07, 08, 09, 11
  - Sun: hours 08–11
  - Mon: hour 19
  - Tue: hours 17–20
  - Thu: hours 16, 18, 19

### D.3 Descriptive findings (S1–S4; never gating)

**In-sample (full-development fit), residual z = (sim − obs) / sd per band.** 41 of 120 components have |z| > 2.

| Band (rps) | Σz² | Components with \|z\| > 2 |
|---|---|---|
| 3–10 | 107 | 11 |
| 10–30 | 63 | 3 |
| 30–60 | 150 | 10 |
| 60–120 | 393 | 17 |

The pattern is the same in all 11 fits:
- **S1 is matched well.** Every |z| ≤ 1.3, except at long windows above 30 rps (W = 30 s and 60 s; z −2.3 to −4.3).
- **S2: the ACF shape doesn't fit.**
  - Lag 1 is too low in every band (z −1.6 to −4.6).
  - Lags 2–5 are mostly too high, most clearly below 30 rps.
  - Lags 10–30 are too low above 30 rps (lag 20: z −8.3 and −7.3).
  - Azure's ACF falls off fast at first, then holds a long tail. A single exponential can't produce both.
- **S3 (W = 10 s): the marginal is too right-tailed.** Skewness is too high in all four bands (z +1.5 to +3.5), and excess kurtosis too (z +0.7 to +3.1). This is the Cycle 1 diagnosis, unchanged.
- **S4: top-tail persistence is too high,** strongly at 60–120 rps (top, lag 2: z +12.5). Bottom-tail persistence is close, except at long lags above 30 rps.

**Held out (R2), by fold and band.** S1 is against its frozen band tolerance; "within" counts S2–S4 components against their 2 × SD reporting tolerances.

| Held-out day | 3–10 | 10–30 | 30–60 | 60–120 |
|---|---|---|---|---|
| Fri | S1 ✓; 20/31 within | S1 ✓; 21/31 | S1 ✓; 24/31 | S1 ✗ (1 hour); 8/31 |
| Sat | S1 ✓; 24/31 | S1 ✓; 27/31 | n/a | n/a |
| Sun | S1 ✓; 17/31 | S1 ✓; 26/31 | n/a | n/a |
| Mon | S1 ✓; 20/31 | S1 ✓; 26/31 | S1 ✓; 15/31 | S1 ✓; 17/31 |
| Tue | S1 ✓; 23/31 | S1 ✓; 23/31 | S1 ✗; 17/31 | S1 ✗; 8/31 |
| Thu | S1 ✓; 20/31 | S1 ✓; 19/31 | S1 ✗; 16/31 | S1 ✓; 22/31 |

**Rate-band holdouts** (R3; reported only): S1 max abs error against the frozen tolerance.

| Band | Error | Tolerance | Result |
|---|---|---|---|
| 3–10 | 0.0108 | 0.0924 | within |
| 10–30 | 0.0268 | 0.0315 | within |
| 30–60 | 0.0137 | 0.0128 | **outside** |
| 60–120 | 0.0092 | 0.0065 | **outside** |

**S5 (diagnostic only; never in the loss or the verdict).** Medians over held-out folds:
- **Exceedance:** frequency and duration above +25% are close to Azure in every band. Above +40%, the 60–120 band produces almost none: fraction 7e-5 against 4e-4.
- **Fluid-backlog p99 at s = 1.0, ρ = 0.8:** higher than Azure at 3–10, 10–30 and 60–120 rps (52 vs 40, 72 vs 55, 43 vs 30), and lower at 30–60 (154 vs 180).

Full values are in `evaluation.json` (`per_day.*.descriptive`).

### D.4 Operational findings (the frozen queue validator; the verdict)

G is the aggregate model/Azure ratio per cell and percentile. ✓ means within the 1/1.40–1.40 band.

| Fold | Gating | G range (8 values) | Worst G | C1′ | Criterion 3 (≥ 80%) | One-sided near-zero (≤ 10%) | Safety (0.5–2.0) | Fold |
|---|---|---|---|---|---|---|---|---|
| Fri | yes | 1.145–1.510 | 1.510 (s 1.0, ρ 0.6, p99) | ✗ | 78.2% ✗ | 1.6% ✓ | ✓ | **FAIL** |
| Mon | yes | 0.823–1.188 | 0.823 | ✓ | 87.4% ✓ | 1.0% ✓ | ✓ | PASS |
| Tue | yes | 0.737–1.075 | 0.737 (s 1.0, ρ 0.6, p99) | ✓ | 90.5% ✓ | 1.6% ✓ | ✓ | PASS |
| Thu | yes | 0.942–1.150 | 1.150 | ✓ | 83.9% ✓ | 2.1% ✓ | ✓ | PASS |
| Sat | reported | 0.692–1.083 | 0.692 (s 1.0, ρ 0.6, p95) | ✗ | 83.7% | 2.2% | ✓ | (fail) |
| Sun | reported | 0.741–1.104 | 0.741 | ✓ | 85.4% | 2.6% | ✓ | (pass) |

All 8 G values for each fold are in `evaluation.json` (`validation_gating`, `validation_reported`).

**Verdict: PASS.**
- Three of the four gating folds pass (Mon, Tue, Thu).
- No gating fold violates the safety condition.
- B = 1.40 and every other rule were applied unmodified through `cycle2_validation.validate`.

**What a PASS means.** This is the frozen resolution statement, and it's the only supported reading:
> No queue-behaviour discrepancy was detected at the resolution supported by the preregistered validation procedure.

It doesn't establish that D matches Azure. The 200-replicate audit shows the rule:
- generally doesn't detect global biases of about 1.15× (8–13%);
- has limited power at about 1.25× (44–46%).

D's gating-fold G values lie between 0.74 and 1.51. This is internal validation on development data that informed Cycle 1's diagnosis and this cycle's design (section 6). It isn't out-of-sample evidence.

**Plumbing checks** (verification only; nothing was tuned on them):
- The Azure p95/p99 values for all 4 × 192 gating-fold cell-metrics are identical to the criterion audit's.
- The Poisson-control medians agree with the audit's independent Poisson controls: geometric-mean ratio 0.990–1.006 per fold.

**Context, not a candidate result.** The frozen rule was applied to the Cycle 1 C1 model outputs already stored in `criterion-audit.json`. Those use the Cycle 1 parameters, the `edge` scenario and audit seeds.
- C1 passes Mon and Tue only. It fails Fri (G up to 1.56) and Thu (G up to 1.58).
- So, under this rule, D's pass hinges on the Thursday fold.
- D's Thu fold fit (a 0.388, τ 10.8 s) has lower σ than C1 (a 0.441), and its Thu G values are 0.94–1.15.

This comparison was computed for this ledger from committed audit data and isn't a gate.

### D.5 Optimiser limitations versus model-family limitations (A3 addendum 2)

**Evidence against an optimiser explanation:**
- Every fit converged well under the cap (≤ 168 of 300 evaluations).
- No best point lies near a bound, under the wide domain the owner chose.
- The 11 fits agree closely: same region, stable parameters, Cycle 1 start lowest.
- Starts 1–7, spread across the domain, were all 6.5–12× worse than the region the fits converged to.

**Limit of that evidence:** the frozen procedure runs Nelder–Mead from one start. So a better, distant minimum can't be excluded, only judged unlikely given the start objectives.

**Evidence for a model-family explanation of the descriptive misfit:** the residual pattern is the same in every fit and every band:
- an ACF too low at lag 1 and too short at long lags;
- skewness and kurtosis too high;
- top-tail persistence too high.

A single OU timescale and a lognormal link can't produce these together at any (a, b, τ). That's consistent with the Cycle 1 diagnosis and with the motivation for Candidate A. **Under the frozen procedure,** the descriptive inadequacy is attributed to the model family rather than the optimiser.

None of this changes the label (A3.4): the descriptive misfit is reported, and the queue validator decides. F1 doesn't apply: D doesn't fit its in-sample targets within 2 × sd, and it passed the queue rule.

### D.6 Status after D

- D is frozen as run. No D2 or D3 exists, and none may be created without separate authorisation (A3.11).
- Candidates A and B haven't been started, implemented or evaluated. They wait for explicit authorisation.
- Wednesday is closed. Section 10 lists the conditions for opening it; among them, A3's selection and freeze steps and the owner's explicit written authorisation haven't happened.
- The next decision is the owner's: section 8 selection, given that A and B haven't been run, and whether to authorise them.

### D.7 Correction (2026-10-08): scope of the model-family statements and the Cycle 1 comparison

- **Requested by:** hydrangeas20, 2026-10-08.
- **Append-only.** It doesn't edit D.1–D.6.
- **What doesn't change:** D's fits, results, verdict (PASS) and the frozen validation criteria.

**1. Persistent structural mismatch isn't proof of impossibility.** Three statements above are stronger than the evidence supports:
- D.3: "A single exponential can't produce both".
- D.5: "A single OU timescale and a lognormal link can't produce these together at any (a, b, τ)".
- D.5: "the descriptive inadequacy is attributed to the model family rather than the optimiser".

They are replaced, for interpretation, by this:

> Under the frozen procedure, the same pattern of descriptive mismatch persisted at every fitted point found, in all 11 fits:
> - S2: lag-1 autocorrelation too low, and too little long-lag autocorrelation above 30 rps;
> - S3 (10 s): skewness and excess kurtosis too high in every band;
> - S4: top-tail persistence too high.
>
> The fits converged well inside the budget and far from every bound, and agreed with each other. **That's evidence of a persistent structural mismatch under the frozen optimiser.** It is **not** proof that no (a, b, τ) in the domain reproduces the targets.

Why it's not proof:
- **The search was local.** Nelder–Mead ran from one start per fit. No global search, profile or exhaustive exploration of the domain was done, and none may be added for D (A3.11).
- **The link is only part of the chain.** The lognormal link ties the multiplier's skewness to σ, as σ(σ² + 3). But S2–S4 are measured on detrended, Poisson-thinned counts aggregated over 1–10 s, not on the multiplier itself. So the link's property doesn't by itself fix the observed statistics.
- **The diagnosis memo said the same.** It records the link-causes-skew mechanism as a hypothesis, not a demonstrated fact (phase-2-queueing-diagnosis.md, section D).

**2. The retrospective Cycle 1 comparison is exploratory.** The D.4 paragraph "Context, not a candidate result", including "D's pass hinges on the Thursday fold", is **retrospective and exploratory**:
- It wasn't preregistered.
- It applies the frozen rule to Cycle 1 C1 outputs produced under different parameters, a different out-of-range scenario (`edge`) and different (audit) seeds.
- It supports no causal claim about why D passed, and plays no role in any verdict or selection.

Any later reference to it must carry the label **exploratory**.
