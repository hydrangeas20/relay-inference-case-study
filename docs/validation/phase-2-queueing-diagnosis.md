# Phase 2: why C1 and C2 fail the queueing test

- **Date:** 2026-09-29
- **Status:** Diagnostic memo. A proposal for review, not a decision.
- **Data:** training days (Fri–Tue) and Thursday only. **No Wednesday timestamp or statistic was computed** (see H for exactly what the loader touches).
- **Coverage:** training-day runs cover C1 and Poisson only. C2 was run on Thursday only.
- **Scope:** diagnosis only. Nothing here tunes C1 or C2, defines a new candidate, changes a threshold or searches parameters ([Amendment 2](phase-2-preregistration.md#amendment-2-2026-09-29-after-thursday-validation), A2.4).
- **Reproduce:** `uv run python analysis/diagnose_queueing.py` (about 15 minutes), then `uv run --with matplotlib python analysis/plot_diagnosis.py`. Output: `analysis/results/diagnosis-queueing/`.

**Labels used here:**

- **OBSERVED:** a measured difference.
- **ASSOCIATION:** a correlation across hours.
- **MECHANISM:** supported by a controlled surrogate experiment. Each experiment swaps or scrambles one *aspect* of an arrival stream (its per-second count distribution, or its time order beyond a block size) while keeping the rest. A positive result shows that aspect is sufficient to move the queue tail. It doesn't prove the aspect is the only cause, and it doesn't isolate which feature *within* that aspect matters.
- **HYPOTHESIS:** untested, or supported only by theory.

## Summary

C1 and C2 match Azure's count variance over 1–30 s windows within about 7%. That's the second-order property they were fitted to. Their autocorrelation is similar but not identical in shape: higher at 5 s, lower at 1 s and (on Thursday) at 20 s. Surrogate experiments show that two aspects of the model's traffic are each **sufficient** to raise queue tails, and the fitted curve constrains neither:

1. **Its per-second count distribution** (MECHANISM, E1b). The observed difference is a more right-skewed, heavier-tailed 5–10 s rate distribution (OBSERVED). This is consistent with, but not shown to be caused by, the log-normal link (HYPOTHESIS).
2. **Its time structure at 5–30 s** (MECHANISM, E1a and E2). One observed difference at these scales is that high-rate states persist longer than Azure's at 2–5 s, while low-rate states match (OBSERVED). That this *specific* asymmetry is what matters is a HYPOTHESIS: the experiments scramble all time structure, not just high-state persistence. For C2, the time-order effect is smaller (E1a: 1.13× vs C1's 1.37× at s 1.0, ρ 0.8).

Sub-second placement was tested and has no effect (E0). The estimator reads the model's σ correctly at Thursday's rates. Each hour's own σ mismatch shows no association with the error (a null result on 24 hours, not proof of no effect). **For C1, the overshoot also appears on the training days**, so it isn't a Thursday artefact. C2 wasn't run on training days.

## A. Strongest observed differences

Medians over hours. "Model" is C1 on the same trend and seed scheme as the validation. On Thursday, C2's arrival statistics are within a few percent of C1's, but its p99 ratios differ by up to about 11% (for example 1.64 vs 1.47 at s 1.0, ρ 0.6). Training has 119 hours (C1 and Poisson only), Thursday 24.

| Statistic | Azure (training) | C1 (training) | Azure (Thursday) | C1 (Thursday) | What it shows |
|---|---|---|---|---|---|
| p99 wait ÷ Azure (s 1.0, ρ 0.8) | 1 | **1.29** | 1 | **1.47** | Overshoot on both splits. Poisson: 0.20 and 0.18 |
| 10 s rate: skewness | 0.29 | **0.42** | 0.21 | **0.34** | Model more right-skewed |
| 10 s rate: excess kurtosis | 0.10 | **0.32** | 0.12 | **0.20** | Model heavier-tailed |
| 10 s rate: 99.9th percentile (relative) | 0.55 | **0.60** | 0.46 | 0.47 | Model upper tail higher |
| P(still in top 5% after 5 s) | 0.14 | **0.20** | 0.17 | **0.21** | High states persist longer |
| P(still in bottom 5% after 5 s) | 0.14 | 0.15 | 0.17 | 0.18 | Low states match |
| Mean run above +2 SD (10 s smoothed) | 4.9 s | **5.4 s** | 4.7 s | **5.4 s** | Longer high excursions |
| Excursions above +40% per hour (5 s smoothed) | 40 | 40 | 15 | **19** | More large excursions (Thursday) |
| Autocorrelation at lag 1 s / 5 s | 0.36 / 0.16 | 0.30 / **0.20** | 0.39 / 0.21 | 0.35 / 0.22 | Different shape: Azure decays faster at 1–5 s |
| Autocorrelation at lag 20 s | 0.046 | 0.041 | 0.083 | **0.042** | Azure keeps more at 20 s (Thursday) |
| Fano factor 1 / 10 / 30 s | 1.53 / 4.70 / 7.28 | 1.48 / 4.58 / 7.36 | 1.57 / 5.23 / 9.20 | 1.60 / 5.42 / 8.90 | **Matches** (the fitted property) |
| Fano factor 0.25 s | 1.04 | **1.12** | 1.08 | **1.16** | Model has extra sub-second variance… |
| Gap coefficient of variation | 1.03 | 1.04 | 1.02 | 1.03 | …but gaps look alike |

**OBSERVED, by condition** (Thursday validation cells, 20 seeds; [figure 1](../../analysis/results/diagnosis-queueing/fig1-queue-error-by-condition.png)):

| | C1 median p99 ratio | C1 cells in band | Poisson median p99 ratio |
|---|---|---|---|
| Service time 0.2 s | 1.22 | 27/48 | 0.52 |
| Service time 1.0 s | **1.46** | 17/48 | 0.21 |
| Utilisation 60% | 1.19 | 31/48 | 0.57 |
| Utilisation 80% | **1.46** | 13/48 | 0.23 |

The model error is largest where Poisson's error is also largest: where rate fluctuations, not per-request randomness, set the queue tail.

**OBSERVED, by rate band.** The band pattern **isn't stable across splits**:

| Split, condition | 3–10 rps | 10–30 | 30–60 | 60–120 |
|---|---|---|---|---|
| Thursday, all cells (hours) | **1.94** (4) | 1.14 (10) | 1.11 (4) | 1.33 (6) |
| Training, 1.0 s, ρ 0.8 (hours) | 1.26 (33) | 1.24 (54) | 1.17 (18) | **1.73** (14) |

The Thursday low-rate figure rests on 4 hours. There's no consistent evidence of a problem specific to low rates.

## B. Quantitative evidence for causes

Each experiment changes one thing and measures C1's p99 relative to Azure's original p99. Medians over 24 Thursday hours; [figure 4](../../analysis/results/diagnosis-queueing/fig4-surrogates.png).

| Experiment (s 1.0, ρ 0.8) | C1 ÷ Azure | Reading |
|---|---|---|
| C1 as generated | 1.47 | Baseline |
| **E0:** arrivals re-placed uniformly within each second (per-second counts kept) | 1.48 | Sub-second structure doesn't matter. Azure itself: 1.00× under the same treatment |
| **E1a:** C1's time order, Azure's per-second count distribution | 1.37 | Fixing the distribution alone removes about a fifth of the log overshoot |
| **E1b:** Azure's time order, C1's per-second count distribution | 1.11 | C1's distribution alone causes some overshoot |

The same pattern holds at 0.2 s, ρ 0.8: 1.46, 1.45, 1.32 and 1.16.

**E2: block shuffle** ([figure 2](../../analysis/results/diagnosis-queueing/fig2-block-shuffle.png)). Per-second counts are shuffled in blocks of B seconds within each 10-minute window. This keeps the trend and the count distribution, but destroys structure longer than B.

| Block size kept intact | 1 s | 5 s | 15 s | 30 s | 60 s | Unshuffled |
|---|---|---|---|---|---|---|
| C1 ÷ Azure, s 1.0, ρ 0.8 | 1.15 | 1.25 | 1.39 | 1.59 | 1.64 | 1.53 |
| C2 ÷ Azure, s 1.0, ρ 0.8 | 1.14 | 1.24 | 1.39 | 1.43 | 1.42 | 1.39 |

(The unshuffled value uses 3 seeds, so it differs slightly from the 5-seed baseline above.) Most of the overshoot builds up from structure at **5–30 s**, the scale of the persistence difference. The 1 s value is what the count distribution alone contributes.

**Not supported as explanations:**

- **Sub-second structure and the 250 ms pattern.** E0 changes p99 by 0–4% for Azure and C1. The model's extra variance at 0.25 s is real but doesn't affect these queue tails.
- **Estimator bias.** On C1 traffic at each Thursday hour's trend, the estimator reads σ within −2.3% to +3.1% of the true value (median 1.00). The 7% bias found earlier was on constant-rate synthetic traffic at 10 rps, and doesn't carry over to these rates.
- **Each hour's own burstiness level (null result, not ruled out).** Model σ ÷ the hour's estimated Azure σ has a median of 1.01 (range 0.85–1.20). It isn't associated with the queue error (Spearman −0.07 to +0.34, all permutation p ≥ 0.11, n = 24 hours, or 15 in one condition). This feature uses C1's σ(λ) for both candidates.

## C. Differences that plausibly explain the overshoot

- **MECHANISM (E1b, E2 at 1 s): the per-second count distribution.** OBSERVED: the model's 5–10 s rate distribution is more right-skewed and heavier-tailed. HYPOTHESIS for why: with `exp(sX − s²/2)`, a symmetric Gaussian X becomes a right-skewed multiplier, so when the variance is fixed at Azure's, the model puts more mass in large upward excursions. E1b swaps the whole distribution, so skew, kurtosis and upper quantiles move together. At 80% utilisation the queue only grows when the rate exceeds 1.25× the trend, so a heavier upper tail means more and deeper overloads. Giving Azure's time ordering the model's count distribution raises Azure's p99 to 1.11–1.23× (all four conditions).
- **MECHANISM (E1a, E2 at 5–30 s): time structure at 5–30 s.** OBSERVED at those scales: one OU process with τ ≈ 9 s decays more slowly at 2–5 s lags than Azure does, and faster at 20 s lags (Thursday), and C1's top-5% states persist longer than Azure's while its bottom-5% states match. HYPOTHESIS: that the high-state persistence is the part that matters. The shape is two-timescale-like, which the Phase 2 audit had already found fits the curves better. Longer upward excursions would accumulate more backlog. Keeping only the model's ordering and giving it Azure's count distribution still leaves 1.03–1.37×, and 1.32–1.37× at 80% utilisation.
- **ASSOCIATION:** across Thursday hours, the model/Azure ratio of mean run length above +2 SD correlates with the p99 error: Spearman +0.36 to +0.45 in 6 of 8 candidate × condition combinations, permutation p 0.03–0.08. This is exploratory: about 10 features × 8 combinations were examined, so it doesn't survive a multiple-comparison correction. No other feature reached |ρ| 0.35.
- **Why the fit didn't catch this (OBSERVED):** the fitted statistic, CV²(W) for W = 1–60 s, is a function of the autocovariance only (second order). The Fano factors from 1 to 30 s agree within about 7% (they diverge at 60 s on Thursday: 10.5 vs 12.5). Skewness, kurtosis and level-dependent persistence don't enter the fit at all.
- **Why it's worst at 1.0 s and 80% (HYPOTHESIS; the Poisson comparison is OBSERVED):** Poisson's p99 falls to 0.18–0.21× Azure there, which indicates that rate modulation sets the queue tail. With many servers (c = ⌈λs/ρ⌉), the queue behaves like a fluid queue driven by rate excursions, so any excursion error is amplified.

## D. Still hypotheses

- **The log-normal link *causes* the skew excess.** This is consistent with theory and with E1b, but not tested in isolation: E1 swaps whole count distributions, not links.
- **Azure's rate distribution is closer to symmetric because of service-level smoothing,** such as client rate limits, retries or batching.
- **Azure's faster decay at 1–5 s plus slower tail at 20 s reflects two distinct processes,** for example per-user bursts plus a population drift.
- **The low-rate retry/duplicate signal** (identical context sizes in sub-millisecond pairs at 3–10 rps) **is irrelevant to these queue tails.** E0 suggests sub-second structure doesn't matter here, but the duplicates themselves weren't isolated.
- **The 60–120 rps overshoot on training (1.73×, 14 hours) and the 3–10 rps overshoot on Thursday (1.94×, 4 hours) are noise.** Too few hours to tell.

## E. Possible revised model classes (proposals, not implemented)

1. **Two-timescale Gaussian modulation with a lighter-tailed link.** X = a fast OU plus a slow OU (τ of roughly 1–3 s and 20–60 s). The multiplier uses a link less convex than `exp`, for example a softplus or a truncated linear `max(ε, 1 + σY)`, or a skew parameter fitted to the 5–10 s rate distribution.
2. **The same process as today, calibrated on higher-order targets as well.** Keep a parametric Cox process, but fit it on training data to the 1–60 s variance curve **plus** the 5–10 s rate quantiles (or skewness) **plus** tail persistence at 2–10 s.
3. **Markov-modulated Poisson process (2–4 rate states).** State dwell times directly model how long bursts last. Asymmetric up and down behaviour and bounded upward excursions come naturally.
4. **Non-parametric residual bootstrap.** Resample Azure's detrended relative-rate paths from training, in blocks of 60–120 s drawn from the matching rate band, and apply them to Relay's envelope.

## F. Tradeoffs

| | Fixes skew | Fixes persistence shape | Parameters and identifiability | Works outside Azure's range | Main risk |
|---|---|---|---|---|---|
| 1. Two-timescale plus lighter link | Yes | Yes | ~5 per band; timescales weakly identified | Same scenario scheme as now | Choosing the link is a modelling choice with little data behind it |
| 2. Same process, more calibration targets | Partly: `exp` fixes the skew for a given σ | No: one timescale | Unchanged | As now | Structural limit: may pass the targets and still miss queue tails |
| 3. MMPP | Yes | Yes (dwell times) | States × bands; fitting is harder (EM) | Needs a rule for scaling states | Discrete states may look artificial at low rates |
| 4. Residual bootstrap | Yes, by construction | Yes, by construction | Almost none | **No**: only within Azure's range; the scenarios still apply outside it | Copies Azure's quirks (retries, duplicates); less explainable; resampling from few hours at high rates |

Any of these adds claims that need their own labels: AZURE-DERIVED for fitted components, and PROJECTED outside the observed range.

## G. Proposed fresh validation protocol

1. **New preregistration first**, committed before any revised candidate is fitted. It would name at most two candidates, the fitting targets, and every threshold.
2. **Data.** Thursday has now been used heavily for diagnosis, so it can't serve as a clean validation day again. Proposed:
   - **Development and validation:** leave-one-day-out cross-validation over the six non-Wednesday days (Fri, Sat, Sun, Mon, Tue, Thu). Each fold refits the candidate without the held-out day and runs the §6 band checks and the §7 queueing test on it.
   - **Pass rule:** a candidate passes validation only if it meets the unchanged thresholds, aggregated over the weekday folds (Fri, Mon, Tue, Thu), with the rule stated in the preregistration.
   - **Final test:** Wednesday stays the single held-out day, evaluated once.
   - **Disclosure:** the preregistration must say that all six days informed this diagnosis, so cross-validation isn't pristine for choosing the model class. Wednesday is the only clean test.
3. **Thresholds are unchanged:** p95/p99 ratio 0.67–1.5 in ≥ 80% of cells, no cell outside 0.5–2.0, and beating Poisson in ≥ 80% of informative cells under the clarified criterion 3. No retuning to make a candidate pass.
4. **Preregistered diagnostics** (reported, not gating): 10 s rate skewness and quantiles, top/bottom-5% persistence at 1–20 s, and the E0/E1 surrogates. A candidate that passes the queueing test while missing these gets flagged.
5. **Gate** (Amendment 2, A2.2): Wednesday runs once, only if a candidate passes validation.

## H. Wednesday

No Wednesday timestamp, token count or statistic was computed for this memo. Every script here calls `load_split` only with `training` or `validation`, and `load_split("holdout")` raises without `allow_holdout`. To be exact about what the loader touches: when it builds a cache, it hashes the whole raw file (the SHA-256 check) and reads each line as text to drop other days by date prefix. So Wednesday's bytes pass through the hash and the prefix filter, but no Wednesday field is parsed. This run used existing caches. The local cache holds only `training.npz`, `training_hours.npy` and `validation.npz`. The next development cycle can also leave Wednesday untouched. The protocol in G uses only the six other days until its gate is passed, and `validate.py --holdout` refuses without a non-provisional pass.
