# Exploratory verification audit, 2026-09-28 (all seven days)

This audit ran **before** the training / validation / holdout split existed, on all seven days of Azure's trace, including Wednesday 05-15 (now the holdout). It's recorded here for transparency. Its pooled numbers are not used by the revised model, which is fitted on training days only (`analysis/azure_traffic.py`). No Wednesday-specific result was inspected; the only hours inspected individually were Mon 16:00, Tue 08:00, Tue 18:00 and Sat 19:00 UTC, all now training days.

The scripts that produced it were later rewritten as `analysis/audit_*.py` with the holdout guard. Rerunning those now gives training-only numbers (`../audit-training/`).

## Findings (all AZURE-DERIVED unless marked; all days, raw timestamps unless noted)

**Burstiness (pooled, ≥ 10 rps hours, n = 126)**
- Pooled fit: σ = 0.161, τ = 8.6 s. Bootstrap 95% CI: σ 0.148–0.173, τ 7.7–10.1 s.
- By rate band: 0.23 (3–10 rps), 0.186 (10–30), 0.126 (30–60), 0.105 (60–120). Rank correlation of per-hour σ with rate: −0.95. Power law slope −0.37.
- Detrending window 300 → 1800 s moves τ from 6.6 to 12.4 s; σ from 0.158 to 0.166.
- Out of sample (fit Fri–Mon, test Tue–Thu): max error 0.037.
- Two-timescale OU fits the six points as well as single OU (log SSE 0.0054 vs 0.0063); power law worse (0.047).
- Estimator recovers known σ within 0.004–0.011 at 10–300 rps (SIMULATED).

**Matched-rate comparison, Tue 18:00 (83 rps), pooled-σ model (SIMULATED vs AZURE-DERIVED)**
- Rate fluctuation at 1 s: model 0.168, Azure 0.092.
- Queue p99 wait (8 servers, 85% utilisation): model 73×, Azure 6.0×, Poisson 1.8× service time.

**Sub-second structure**
- Gaps < 1 ms: 45.1% at Tue 18:00 vs 7.9% for Poisson; 6–9× Poisson in every rate band.
- 0.013% of all 16.8M arrivals fall in the last 50 ms of each 250 ms interval.
- No exact duplicate timestamps; microsecond digits uniform.

**Scale and sizes**
- Smooth-curve peak 2,433.52 rps (CALCULATED); Azure weekday peak-hour/mean-hour 2.14–2.32 vs Relay 2.05.
- Azure full trace: median prompt 1,930 tokens, median output 8, p99 output 271.
- Built prompts (pre-revision generator): KS 0.060 vs Azure sample (fail); 5.3% of targets inflated, 2.0% short.

**Friday is a complete day** (8.61× peak/trough), contrary to an earlier code comment.
