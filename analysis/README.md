# Analysis: from Azure's raw trace to fitted parameters, and how they're tested

Everything the traffic model takes from Azure's data is produced here, reproducibly, from the SHA-256-verified raw trace. The raw trace (~690 MB) isn't committed.

## 1. Get the raw data

```bash
uv run python analysis/azure_download.py        # downloads and verifies the SHA-256
```

- **Source:** Azure LLM inference trace 2024, code service, one week (CC-BY 4.0; Stojkovic et al., DynamoLLM, HPCA 2025).
- **File:** `data/azure/AzureLLMInferenceTrace_code_1week.csv` (gitignored)
- **SHA-256:** `71de5c55cbc35f8f1ed0b6b7806b4cd1e9764b0058469725a6aac98023a1448f`, 16,803,695 rows

## 2. The data split and the holdout guard

| Split | Days (UTC) | Used for |
|---|---|---|
| training | Fri 05-10 … Tue 05-14 | Fits, thresholds, reference artifacts |
| validation | Thu 05-16 | Choosing between candidates |
| holdout | Wed 05-15 | Evaluated exactly once, only after written authorisation |

`common.load_split()` drops Wednesday rows by date prefix before parsing anything, and raises `HoldoutAccessError` unless `allow_holdout=True`. Only `validate.py --holdout` passes it. Parsed splits are cached in `data/azure/cache/` (gitignored); there is no Wednesday cache until the holdout run.

Burstiness analyses use **de-jittered** timestamps (each redrawn uniformly within its 250 ms interval, seed 20260928; see ADR-0005 D2). The sub-second audit and the clustered variant use **raw** timestamps.

## 3. The chain

| Step | Script | Input | Output | Committed |
|---|---|---|---|---|
| Raw → reference data | `azure_traffic.py` | training split | `traffic/reference/*.{csv,json}`: hourly counts, size sample, per-band statistics, candidate fits C1/C2, observed range, tolerances, clustering statistics | Yes |
| Reference → model | `src/relay/traffic/` | reference data + `traffic/relay.toml` | the traffic model used by `relay-trace` | Yes |
| In-sample check | `make traffic-check` | reference data | generator reproduces training band curves | printed |
| Validation (preregistered) | `validate.py` | validation split (and, once, holdout) | `results/validation-<split>.json` | Yes |
| Prompt fidelity (preregistered, Amendment 1) | `validate_prompt_fidelity.py` | code corpus + reference sizes | `results/validation-prompt-fidelity-amended.json`; the first, pre-amendment result stays in `results/validation-prompt-fidelity.json` and is never overwritten | Yes |
| Sensitivity (preregistered, descriptive) | `sensitivity.py` | selected candidate | `results/sensitivity.json` | Yes |
| Criterion 3 clarified (Amendment 2) | recomputed from stored cells | `results/validation-validation.json` | `results/validation-validation-criterion3-clarified.json` | Yes |
| Queueing-failure diagnosis (Amendment 2, A2.4) | `diagnose_queueing.py` | training + validation splits (never holdout) | `results/diagnosis-queueing/diagnosis.json`; memo in `docs/validation/phase-2-queueing-diagnosis.md` | Yes |
| Cycle 2 frozen queue-validation rule (Amendment 1) | `cycle2_validation.py` | candidate and Azure queue metrics per gating fold | verdict plus the measurement-resolution statement; pinned by `cycle2_validation_freeze.json` | Yes |
| Diagnosis figures | `plot_diagnosis.py`, run with `uv run --with matplotlib` (matplotlib isn't a project dependency) | `diagnosis.json` | `results/diagnosis-queueing/fig*.png` | Yes |

The one estimator used everywhere is `relay.traffic.stats.rate_cv2`. `validation_config.py` holds the frozen preregistration values; `validate.py` and `sensitivity.py` refuse to run while preregistration items are unresolved.

## 4. Audit scripts

These are the evidence behind ADR-0005. All default to the **training** split and can't read the holdout.

| Script | What it shows |
|---|---|
| `audit_burstiness.py` | Per-hour fits and rate dependence, bootstrap CIs, detrending sensitivity, alternative models, estimator recovery on synthetic traffic |
| `audit_matched_rate.py` | One Azure hour vs the model driven by that hour's trend vs Poisson: rate fluctuation, autocorrelation, queue waits |
| `audit_subsecond.py` | Sub-millisecond gaps, duplicates, microsecond digits, 250 ms phase structure, cluster statistics |
| `audit_scale_and_sizes.py` | The scale chain to peak rps, its sensitivity, size-sample percentiles (independent of the model code) |

`results/audit-training/` holds their output on the training split. `results/audit-2026-09-28/` records the original exploratory audit, which ran on **all seven days** before the split existed; see its README.

## 5. Reproduce everything

```bash
make corpus                                     # code corpus for prompts
uv run python analysis/azure_download.py
uv run python analysis/azure_traffic.py         # regenerate reference data (training only)
make traffic-check
uv run python analysis/validate_prompt_fidelity.py
uv run python analysis/validate.py              # Thursday; needs resolved preregistration
uv run python analysis/sensitivity.py
```
