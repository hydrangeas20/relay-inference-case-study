# ADR-0004: Relay's traffic model

- **Status:** Accepted
- **Date:** 2026-09-28
- **Decided by:** hydrangeas20

Four decisions define how Relay's traffic is modelled. The **Why** lines are the engineer's reasoning and are left for the engineer to write. Reference data comes from Azure's public 2024 code trace (CC-BY 4.0, see `traffic/reference/README.md`).

## 1. Daily shape → C. Parametric, checked against Azure

- **A. Parametric model:** our own formula.
- **B. Azure 2024 week trace:** rescale Azure's real daily pattern.
- **C. Parametric, checked vs Azure** ✅.

**Consequences:** the weekday shape is an overnight floor plus a workday bump for North America (60%) and Europe (40%). The floor (10% of peak) was tuned so the hourly peak/trough ratio is **9.6×**, inside Azure's Mon–Thu range of **9.1×–11.3×**. `make traffic-check` fails if a config change moves it outside that range.

Only the ratio is checked, not the timing. Relay peaks at 15:00 UTC while Azure peaks at 18:00–19:00 UTC; that difference reflects the two services' different user geography, not an error. Weekends aren't modelled (Azure's weekend days carry about 31% of weekday volume with a flatter shape).

**Why:** _to be written_

## 2. Burstiness → C. Fitted bursty model

- **A. Poisson.**
- **B. Replay Azure's inter-arrival gaps.**
- **C. Fitted bursty model** ✅.

**What the data showed:** Azure's arrivals are not a renewal process. Their dispersion grows with the counting window (at a peak hour, variance/mean is 1.9 over 1 s windows but 19.6 over 60 s), which means the *rate itself* wanders. A model that only makes gaps more variable (e.g. gamma-distributed gaps) can't reproduce that.

**Model:** a Cox process. The envelope rate is multiplied by `exp(X − s²/2)`, where X is an Ornstein–Uhlenbeck process. Fitted on 126 busy hours (≥ 10 requests/s) after removing a 10-minute moving-average trend: the rate fluctuates by **±16%** with a **8.5 s** correlation time. The fit matches the observed fluctuation at all six window sizes (1–60 s) to within 0.005.

**Consequences:** the multiplier is relative, so a trace scaled down to one GPU keeps the same burst structure. Burstiness slower than about 10 minutes is left to the envelope. `make traffic-check` confirms generated traces reproduce the fit.

**Why:** _to be written_

## 3. Request sizes → B. Azure for completions only

- **A. Azure for everything.**
- **B. Azure for completions; agent and indexing sizes are ours** ✅.
- **C. Our own ranges for everything.**

**Consequences:** each completion draws a (prompt tokens, output tokens) pair from 20,000 Azure samples (median prompt 1,930 tokens, median output 8, p99 output 271). Prompt tokens become characters at **3.5 characters per token**, an assumption until Phase 3 picks a tokenizer. The prefix size is what's left after the gateway's template and any context files. Each request records its target sizes, and the generator reports how often a prompt falls short because no corpus file is long enough (0% on a 20-minute peak window).

**Why:** _to be written_

## 4. Scaling → C. Two trace types

- **A. Scale the rate.**
- **B. Compress time.**
- **C. Two trace types** ✅.

**Consequences:**

- `relay-trace window --start HH:MM --minutes N --peak-rps R`: a slice of the day for real-GPU runs.
- `relay-trace day --peak-rps R`: 24 hours at real time for the simulator.

Both are scaled by one number: the interactive rate at Relay's daily peak after scaling. At full scale Relay peaks at **2,434 interactive requests/s** (96M completions and 6.4M agent turns a day). The trace header records the scale and how many of Relay's 400K daily users it represents, so every result can say what fraction of Relay it describes.

**Why:** _to be written_

---

## Open questions for the engineer

| # | Question | Current default | Where |
|---|---|---|---|
| Q8 | Relay's assumptions: 4 active hours/day, 60 completions and 4 agent turns per active hour, 60/40 NA/EU split, 200K indexing jobs/night | As listed | `traffic/relay.toml` |
| Q9 | Characters per token until a tokenizer is chosen | 3.5 | `traffic/relay.toml` |
| Q10 | Azure's output lengths are enforced by forcing the model to generate exactly that many tokens. Should real-GPU runs do the same (vLLM `ignore_eos`), or let the model stop naturally with `max_tokens` as a cap? | `max_tokens` is set to the target; nothing forces it | `loadgen`, Phase 3 |
| Q11 | Day traces are large (~840K requests, 270 MB at a peak of 20 rps). The load generator builds every payload before starting, which won't fit in memory for a day trace. Build payloads a few seconds ahead instead, or split day traces into hourly files? | Not solved; day traces can be generated but not yet replayed | `loadgen/runner.py` |
