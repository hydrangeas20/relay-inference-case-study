# RLY-3: "Our GPU bill doubled"

| | |
|---|---|
| **Theme** | Right-sizing and quantization |
| **Status** | Planned |
| **Results source** | `gpu`, `projection` |

## Customer complaint

> "We're spending more every month and don't know why."

## Root cause (planted)

A ~7B model running at FP16 on an oversized GPU chosen "to be safe".

## Reproduce

1. Measure cost per 1K requests at SLO on the current configuration.
2. Establish the FP16 quality baseline on the eval suite.

## Fix

- Benchmark smaller/cheaper GPU types and FP8 quantization.
- Run the full eval suite on every candidate configuration.
- Choose the cheapest configuration that meets both the latency SLO and the quality SLO.

## Acceptance criteria

- [ ] Each configuration reports: cost per 1M output tokens, sustainable request rate at SLO, and eval score.
- [ ] Quality compared to the FP16 baseline with run-to-run variance shown.
- [ ] Recommendation names the configuration and the reason, including what was rejected.

## Proof

Scatter of cost per 1M tokens vs. quality score, one dot per configuration, with the best-value options highlighted.

## Connects to

Its success sets up RLY-6, where someone pushes quantization further without checking.

---

## Findings

*Filled in once the ticket has been worked. Every number links to its file in `results/`.*

### Diagnosis

### What changed

### Before / after

| Metric | Before | After | Source |
|---|---|---|---|

### Recommendation to Relay

### What I'd do with more time
