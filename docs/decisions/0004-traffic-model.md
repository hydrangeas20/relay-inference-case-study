# ADR-0004: Relay's traffic model

- **Status:** Accepted, amended by [ADR-0005](0005-traffic-model-revision.md)
- **Date:** 2026-09-28
- **Decided by:** hydrangeas20

Four decisions define how Relay's traffic is modelled. The **Why** lines are the engineer's reasoning and are left for the engineer to write. Reference data comes from Azure's public 2024 code trace (CC-BY 4.0, see `traffic/reference/README.md`).

Quantitative claims carry the labels defined in [methodology](../methodology.md#claim-labels). Every AZURE-DERIVED figure below comes from the training days (Fri 10 – Tue 14 May 2024) unless it says otherwise. ADR-0005 explains the split.

## 1. Daily shape → C. Parametric, checked against Azure

- **A. Parametric model:** our own formula.
- **B. Azure 2024 week trace:** rescale Azure's real daily pattern.
- **C. Parametric, checked vs Azure** ✅.

**Consequences:** the weekday shape is an overnight floor plus a workday bump for North America (60%) and Europe (40%) (ASSUMED). The floor (10% of peak, ASSUMED) was tuned so the hourly peak/trough ratio is **9.6×** (CALCULATED). That's inside the range of Azure's complete training weekdays, **8.6×–11.3×** (Fri, Mon, Tue; AZURE-DERIVED). `make traffic-check` fails if a config change moves the ratio outside that range.

This is a plausibility check on one number. It doesn't show that Relay's daily shape matches Azure's. It also doesn't check peak-to-mean, which is what drives peak capacity: **2.05** for Relay (CALCULATED) against **2.14–2.32** on Azure's training weekdays (AZURE-DERIVED).

Only the ratio is checked, not the timing. Relay's busiest hour is 15:00–16:00 UTC (the curve peaks at 15:41) while Azure's is 18:00–20:00 UTC. That difference reflects the two services' different user geography, not an error. Weekends aren't modelled: Azure's training weekend days carry about a third of an average training weekday's volume, with a flatter shape (AZURE-DERIVED).

**Why:** _to be written_

## 2. Burstiness → C. Fitted bursty model

- **A. Poisson.**
- **B. Replay Azure's inter-arrival gaps.**
- **C. Fitted bursty model** ✅.

**What the data showed (AZURE-DERIVED):** Azure's arrivals are not a renewal process. Their dispersion grows with the counting window. In the Tue 18:00 UTC hour, the variance/mean of request counts is 1.9 over 1 s windows and 19.6 over 60 s. After removing the within-hour trend it's 1.7 and 10.9, still well above the 4.1 that a renewal process with that hour's gap variability would level off at. So the *rate itself* wanders, and a model that only makes gaps more variable (e.g. gamma-distributed gaps) can't reproduce that.

Burstiness also depends on request rate. Pooled by rate band over the 119 training hours at ≥ 3 rps, the rate's relative standard deviation at 1 s is 0.23 at 3–10 rps, 0.18 at 10–30, 0.12 at 30–60 and 0.11 at 60–120. The first version of this model used one pooled value; ADR-0005 D1 replaces it.

**Model:** a Cox process. The envelope rate is multiplied by `exp(X − s²/2)`, where X is a unit-variance Ornstein–Uhlenbeck process with correlation time τ, and s² = ln(1 + σ²). σ depends on the trace's own expected rate λ through a power law σ = a·λ^b fitted to the training bands. Rates are estimated per second, after removing a 10-minute moving-average trend. Two candidates were fitted on training data only (AZURE-DERIVED) and are chosen between on Thursday, as preregistered:

| Candidate | σ(λ) | τ |
|---|---|---|
| **C1** (baseline; default in `relay.toml`) | 0.441·λ^−0.323 | 9.2 s at every rate |
| **C2** | 0.485·λ^−0.351 | per band: 8.2, 7.5, 11.8, 10.3 s, interpolated in log-rate |

**Observed range.** The power law applies between 3.2 and 82.8 rps, the training hours' range. Outside it, generation needs one of three pre-declared scenarios (ADR-0005 D1): `edge` holds σ at the boundary value, `poisson` sets it to zero, and `trend` extrapolates the power law (PROJECTED). Relay's full-scale peak (about 2,400 rps) is far outside the range, so the scenario is part of every result at that scale. The trace header records the candidate, the range, the scenario and the fraction of time spent out of range.

**Consequences:** the multiplier is relative, so burstiness depends on the rate of the trace actually generated. A trace scaled down to one GPU gets the burstiness Azure shows at *that* rate, not at Relay's full-scale rate. Burstiness slower than about 10 minutes is left to the envelope. `make traffic-check` compares generated traffic with the training bands' pooled curves (in-sample; MEASURED on SIMULATED traces). This shows that the generator implements the fit. It isn't validation. Out-of-sample validation, the queueing test and the choice between C1 and C2 follow the [preregistration](../validation/phase-2-preregistration.md).

**Thursday validation (MEASURED on Azure's Thursday, SIMULATED model traffic; 2026-09-28):** neither candidate passed, so the preregistered selection rule recorded **C2 as a provisional fallback. It is not validated and not the default** (criterion-1 fraction 0.49 against C1's 0.46). Cycle 1 is closed as a **failed validation cycle** without a Wednesday run (preregistration Amendment 2 and Cycle 1 closure). **The burstiness model is unvalidated**, and no traffic-model validation claim may be made. Both candidates' predicted burstiness curves were within tolerance in every Thursday rate band except C1's 30–60 rps band (error 0.0113 against 0.0102), and both passed the rate-band holdouts. **Both failed the queueing test**: criteria 1 and 2 fail; criterion 3 fails as run (58/87) and passes under Amendment 2's clarified rule (73/87), which doesn't change the verdict. Queueing tails came out longer than Azure's: the median model/Azure p99 wait ratio is 1.28, and most out-of-bounds cells are overestimates. Poisson's are far shorter (0.32). The fitted fluctuation curve at 1–60 s doesn't pin down queue tails. Full results: `analysis/results/validation-validation.json`. The Wednesday holdout hasn't been run. The [queueing diagnosis](../validation/phase-2-queueing-diagnosis.md) shows, with surrogate experiments, that the model's per-second count distribution (more right-skewed at 5–10 s) and its time structure at 5–30 s are each sufficient to raise queue tails. Sub-second placement has no effect.

**Known limitations:**

- **The data doesn't identify the OU form.** A two-timescale model fits the training curves slightly better (AZURE-DERIVED).
- **τ depends on the detrending window.** It ranges from 2.2 s (2-minute trend) to 12.6 s (60-minute trend), while σ barely moves (0.187–0.202) (AZURE-DERIVED, pooled training hours).
- **The estimator reads slightly high at low rates.** On simulated traffic with σ = 0.16, it recovers 0.171 ± 0.011 at 10 rps and 0.162 at 80 rps (SIMULATED).
- **Queueing is still more sensitive than Azure's in the one in-sample hour checked.** Driven by the trend of Azure's Tue 18:00 hour (83 rps), C1's 1 s fluctuation is 0.095 against Azure's 0.092 (the pooled model gave 0.17). But its p99 wait in an 8-server queue at 85% utilisation is 11.8 service times, against Azure's 5.8 and Poisson's 2.2 (SIMULATED, one seed). The preregistered queueing test is what decides whether this matters.
- **Possible retries or duplicates at low rates (exploratory, AZURE-DERIVED).** Among pairs of arrivals under 1 ms apart, 11.5% share an identical context size at 3–10 rps, against 2.9% for other pairs. This may be a retry or duplicate component. It doesn't change the canonical model.
- **Sub-second structure is scoped out (ADR-0005 D2).** Azure's raw timestamps show a repeating 250 ms pattern and excess sub-millisecond gaps. Canonical traffic reproduces neither, and is compared with Azure timestamps re-randomised within each 250 ms interval. A `--clustered` variant adds excess clustering without the 250 ms pattern, for sensitivity runs.

**Why:** _to be written_

## 3. Request sizes → B. Azure for completions only

- **A. Azure for everything.**
- **B. Azure for completions; agent and indexing sizes are ours** ✅.
- **C. Our own ranges for everything.**

**Consequences:** each completion draws a (prompt tokens, output tokens) pair from a 20,000-row random sample of Azure's training days (AZURE-DERIVED). In the sample, the median prompt is 1,900 tokens, the median output 8 and the p99 output 269. Output sizes become `max_tokens`, a cap: actual output lengths depend on the model (Q10).

Prompt tokens become characters at **3.5 characters per token** (ASSUMED, temporary until Phase 3 picks a tokenizer). The generator knows the gateway's template, so it builds each prompt to its target size. The gateway reports the built size of every prompt in an `X-Relay-Prompt-Chars` header and a histogram.

**Fidelity (MEASURED, preregistration §8 as amended, A1.3):** on a 60-minute trace at 8 rps, each request counts as representable if its target is at least its own structural minimum (561–636 characters). The built sizes of the 25,372 representable prompts follow the Azure sample, conditioned the same way: the Kolmogorov–Smirnov distance is 0.0046 against a 5% critical value of 0.0131. Every representable prompt is built at exactly its target size in characters. A first run, before the amendment, used one global 636-character cutoff that wasn't preregistered. It gave 0.0060 against 0.0131, and its result is kept.

Targets smaller than the template can build (**5.6%** of completions) are kept and flagged, never resampled. They come out a median 2.3× too large (10th–90th percentile 1.1×–11.7×). The fidelity claim covers representable targets only. The gateway rejects completions with `max_tokens` above 4,096; Azure's sample contains a few (2 of 26,874 requests in that trace).

**Why:** _to be written_

## 4. Scaling → C. Two trace types

- **A. Scale the rate.**
- **B. Compress time.**
- **C. Two trace types** ✅.

**Consequences:**

- `relay-trace window --start HH:MM --minutes N --peak-rps R`: a slice of the day for real-GPU runs.
- `relay-trace day --peak-rps R`: 24 hours at real time for the simulator.

Both are scaled by one number: the interactive rate at Relay's daily peak after scaling. At full scale the smooth curve peaks at **2,434 interactive requests/s** at 15:41 UTC (CALCULATED): 102.4M requests a day (96M completions and 6.4M agent turns, ASSUMED) ÷ 86,400 s × a peak-to-mean ratio of 2.053. This is a scenario output, not a finding. It's before burstiness, so one-second rates exceed it. It scales linearly with daily users, active hours and requests per active hour: at 30, 60 and 90 completions per active hour it's 1,293, 2,434 and 3,574 rps.

The trace header records the scale and the equivalent number of Relay's daily active users, meaning the trace carries the same volume as that many average daily users. These aren't concurrent users. For example, `--peak-rps 8` gives a scale of 0.33%, or 1,315 daily-user equivalents.

Each trace carries three identities (ADR-0005 D7): `spec_id` (what was asked for, with its input hashes), `generator_sha256` (the code and environment that built it) and `trace_id` (a hash of the requests themselves, checked on read).

**Why:** _to be written_

---

## Open questions for the engineer

| # | Question | Current default | Where |
|---|---|---|---|
| Q8 | Relay's assumptions: 4 active hours/day, 60 completions and 4 agent turns per active hour, 60/40 NA/EU split, 200K indexing jobs/night | As listed | `traffic/relay.toml` |
| Q9 | Characters per token until a tokenizer is chosen | 3.5 | `traffic/relay.toml` |
| Q10 | Azure's output lengths are enforced by forcing the model to generate exactly that many tokens. Should real-GPU runs do the same (vLLM `ignore_eos`), or let the model stop naturally with `max_tokens` as a cap? | `max_tokens` is set to the target; nothing forces it | `loadgen`, Phase 3 |
| Q11 | Day traces are large (~840K requests, 270 MB at a peak of 20 rps). The load generator builds every payload before starting, which won't fit in memory for a day trace. Build payloads a few seconds ahead instead, or split day traces into hourly files? | Not solved; day traces can be generated but not yet replayed | `loadgen/runner.py` |
