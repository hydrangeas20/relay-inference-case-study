# RLY-6: "Quality dropped last Tuesday and nobody knows why"

| | |
|---|---|
| **Theme** | Evals and safe rollout |
| **Status** | Planned |
| **Results source** | `gpu` |

## Customer complaint

> "Users say suggestions got worse. Our benchmarks look normal."

## Root cause (planted)

After RLY-3's FP8 win, an engineer pushed INT4 quantization to save more. Aggregate benchmark scores barely moved, but quality dropped on less common languages and long files.

## Reproduce

1. Run the eval suite on the FP8 and INT4 versions.
2. Show the aggregate score barely changing.
3. Break results down by language and file length, and show where the damage is concentrated.

## Fix

- Roll back to FP8.
- Add a canary gate: every model or serving change runs the sliced eval suite and must pass per-slice thresholds before full rollout.

## Acceptance criteria

- [ ] Per-slice eval results (language × file length) for FP8 vs. INT4, with variance.
- [ ] The canary gate is implemented as a runnable check that fails on the INT4 build and passes on FP8.
- [ ] The write-up explains why aggregate metrics missed the regression.

## Proof

Eval score over time with the bad deploy marked, plus a per-slice breakdown showing where the regression hid.

## Connects to

Shows why RLY-3's quality check wasn't optional.

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
