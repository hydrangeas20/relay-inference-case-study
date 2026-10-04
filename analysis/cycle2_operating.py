"""Operating characteristics of the PROPOSED aggregated queue criterion (expanded audit).

Usage: uv run python analysis/cycle2_operating.py

Reads only analysis/results/cycle2/criterion-audit-200.json.gz (the 200-replicate
perfect-model null; no Azure data, no candidate). Everything evaluated here was
predeclared in cycle2_config.AUDIT_EXPANDED and in section 5 of
docs/validation/phase-2-cycle-2-criterion-audit.md before the audit ran:

  bounds   B in (1.25, 1.30, 1.35, 1.40), the only equivalence bounds evaluated
  biases   b in (1.15, 1.25, 1.30, 1.50), multiplying the null model's p95/p99:
           globally (every cell and percentile), or confined to one of the 8
           cell-and-percentile combinations at a time
  fold     passes if: all 8 geometric-mean ratios G within [1/B, B] (C1'),
           criterion 3 (clarified, unchanged), and one-sided near-zero hours
           <= 10% of the fold's cell-metrics
  rule     >= 3 of the 4 gating folds pass, and no fold has a G outside
           [0.5, 2.0] (proposed safety bound C2')

Rejection probability = 1 - P(rule passes). Intervals are 95% Wilson score intervals.
"""

from __future__ import annotations

import gzip
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

import cycle2_config as cfg

IN = Path("analysis/results/cycle2/criterion-audit-200.json.gz")
OUT = Path("analysis/results/cycle2/criterion-audit-200-operating.json")
CELLS = [(s, rho) for s in cfg.SERVICE_TIMES_S for rho in cfg.UTILISATIONS]
METRICS = ("p95", "p99")
EXP = cfg.AUDIT_EXPANDED


def wilson(k: int, n: int, z: float = 1.959964) -> tuple[float, float]:
    """95% Wilson score interval for k successes in n trials."""
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (max(0.0, centre - half), min(1.0, centre + half))


def _thresholds() -> np.ndarray:
    """Near-zero threshold 0.01 * s, shaped (cells, metrics)."""
    return np.array([[0.01 * s] * len(METRICS) for s, _ in CELLS])


def evaluate(model: np.ndarray, poisson: np.ndarray, ref: np.ndarray) -> dict[str, np.ndarray]:
    """Per-(replicate, fold) quantities.

    model, poisson: (F, H, C, K) medians; ref: (R, F, H, C, K) single realisations.
    Returns arrays shaped (R, F): max_abs_log_g, onesided_fraction, criterion_3,
    and log_g shaped (R, F, C, K).
    """
    thr = _thresholds()
    m = np.broadcast_to(model, ref.shape)
    p = np.broadcast_to(poisson, ref.shape)
    low_m, low_a, low_p = m < thr, ref < thr, p < thr
    informative = ~low_m & ~low_a
    onesided = low_m ^ low_a
    with np.errstate(divide="ignore", invalid="ignore"):
        log_r = np.where(informative, np.log(m / ref), 0.0)
    n_inf = informative.sum(axis=2)
    log_g = np.where(n_inf > 0, log_r.sum(axis=2) / np.maximum(n_inf, 1), 0.0)
    # Criterion 3, clarified (Cycle 1 Amendment 2, A2.3); must equal queueing.judge_cell.
    with np.errstate(divide="ignore", invalid="ignore"):
        m_err = np.where(low_m & low_a, 0.0,
                         np.where(onesided, np.inf, np.abs(np.log(m / ref))))  # fmt: skip
        p_err = np.where(low_p & low_a, 0.0,
                         np.where(low_p ^ low_a, np.inf, np.abs(np.log(p / ref))))  # fmt: skip
    informative3 = ~(low_m & low_a)
    beats_metric = (m_err < p_err) | ~informative3
    any_inf = informative3.any(axis=-1)  # (R, F, H, C)
    beats_cell = beats_metric.all(axis=-1) & any_inf
    non_tie = any_inf.sum(axis=(2, 3))
    beats = beats_cell.sum(axis=(2, 3))
    c3 = (non_tie > 0) & (beats >= 0.8 * non_tie)
    return {
        "log_g": log_g,
        "max_abs_log_g": np.abs(log_g).max(axis=(2, 3)),
        "onesided_fraction": onesided.mean(axis=(2, 3, 4)),
        "criterion_3": c3,
        "beats_fraction": beats / np.maximum(non_tie, 1),
    }


def rule_outcomes(ev: dict[str, np.ndarray], bound: float) -> dict[str, np.ndarray]:
    lo, hi = EXP["safety_bounds"]
    c1p = ev["max_abs_log_g"] <= math.log(bound)
    cap = ev["onesided_fraction"] <= EXP["nearzero_cap"]
    c3 = ev["criterion_3"]
    safety = (ev["log_g"] < math.log(lo)) | (ev["log_g"] > math.log(hi))
    safety_fold = safety.any(axis=(2, 3))
    fold_pass = c1p & c3 & cap
    rule = (fold_pass.sum(axis=1) >= cfg.FOLDS_REQUIRED) & ~safety_fold.any(axis=1)
    rule_no_safety = fold_pass.sum(axis=1) >= cfg.FOLDS_REQUIRED
    return {"c1p": c1p, "cap": cap, "c3": c3, "safety_fold": safety_fold,
            "fold_pass": fold_pass, "rule": rule, "rule_no_safety": rule_no_safety}  # fmt: skip


def _rate(x: np.ndarray) -> dict[str, Any]:
    k, n = int(np.sum(x)), int(np.size(x))
    lo, hi = wilson(k, n)
    return {"p": round(k / n, 4), "ci95": [round(lo, 4), round(hi, 4)], "k": k, "n": n}


def load_arrays(record: dict[str, Any], truth: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    folds = record["folds"]
    hours = {len(f["hours"]) for f in folds}
    if len(hours) != 1:
        raise ValueError(f"folds have different hour counts: {hours}")

    def arr(cells: list[dict[str, float]]) -> list[list[float]]:
        return [[c[k] for k in METRICS] for c in cells]

    model = np.array([[arr(h[truth]["model"]) for h in f["hours"]] for f in folds])
    poisson = np.array([[arr(h["poisson"]) for h in f["hours"]] for f in folds])
    reps = len(folds[0]["hours"][0][truth]["references"])
    ref = np.array(
        [[[arr(h[truth]["references"][r]) for h in f["hours"]] for f in folds] for r in range(reps)]
    )
    return model, poisson, ref


def main() -> None:
    record = json.loads(gzip.decompress(IN.read_bytes()))
    weekdays = [f["weekday"] for f in record["folds"]]
    combos = [(i, j) for i in range(len(CELLS)) for j in range(len(METRICS))]
    out: dict[str, Any] = {"source": str(IN), "predeclared": {k: v for k, v in EXP.items()},
                           "replicates": record["replicates"], "seed_entropy": record["seed_entropy"],
                           "truths": {}}  # fmt: skip
    for truth in cfg.AUDIT_TRUTH_PROCESSES:
        model, poisson, ref = load_arrays(record, truth)
        null = evaluate(model, poisson, ref)
        t: dict[str, Any] = {"null": {}, "power": {}}
        for b in EXP["bounds"]:
            o = rule_outcomes(null, b)
            t["null"][str(b)] = {
                "P_rule_3_of_4": _rate(o["rule"]),
                "P_rule_without_safety": _rate(o["rule_no_safety"]),
                "P_all_4_folds_pass": _rate(o["fold_pass"].all(axis=1)),
                "fold_pass": {w: _rate(o["fold_pass"][:, i]) for i, w in enumerate(weekdays)},
                "fold_failure_by_criterion": {
                    "C1_prime": {w: _rate(~o["c1p"][:, i]) for i, w in enumerate(weekdays)},
                    "criterion_3": {w: _rate(~o["c3"][:, i]) for i, w in enumerate(weekdays)},
                    "nearzero_cap": {w: _rate(~o["cap"][:, i]) for i, w in enumerate(weekdays)},
                },
            }  # fmt: skip
        o = rule_outcomes(null, EXP["bounds"][0])
        t["safety_bound"] = {
            "per_fold_false_failure": {w: _rate(o["safety_fold"][:, i]) for i, w in enumerate(weekdays)},
            "family_false_failure_any_fold": _rate(o["safety_fold"].any(axis=1)),
            "comparisons_per_replicate": len(weekdays) * len(combos),
            "max_abs_G_factor_quantiles_50_90_99_max": np.exp(
                np.quantile(null["max_abs_log_g"].max(axis=1), [0.5, 0.9, 0.99, 1.0])).round(3).tolist(),
        }  # fmt: skip
        t["nearzero_cap"] = {
            "per_fold_false_failure": {w: _rate(~o["cap"][:, i]) for i, w in enumerate(weekdays)},
            "any_fold_exceeds": _rate((~o["cap"]).any(axis=1)),
            "two_or_more_folds_exceed": _rate((~o["cap"]).sum(axis=1) >= 2),
            "onesided_fraction_quantiles_50_99_max": np.quantile(
                null["onesided_fraction"], [0.5, 0.99, 1.0]).round(4).tolist(),
        }  # fmt: skip
        t["criterion_3"] = {
            "per_fold_failure": {w: _rate(~null["criterion_3"][:, i]) for i, w in enumerate(weekdays)},
            "any_fold_fails": _rate((~null["criterion_3"]).any(axis=1)),
            "beats_fraction_quantiles_1_50": np.quantile(null["beats_fraction"], [0.01, 0.5]).round(4).tolist(),
        }  # fmt: skip
        for bias in EXP["biases"]:
            scen: dict[str, Any] = {}
            ev = evaluate(model * bias, poisson, ref)
            scen["global"] = {str(b): _rate(~rule_outcomes(ev, b)["rule"]) for b in EXP["bounds"]}
            local: dict[str, Any] = {}
            for i, j in combos:
                factor = np.ones((len(CELLS), len(METRICS)))
                factor[i, j] = bias
                ev = evaluate(model * factor, poisson, ref)
                name = f"s{CELLS[i][0]}_rho{CELLS[i][1]}_{METRICS[j]}"
                local[name] = {str(b): _rate(~rule_outcomes(ev, b)["rule"]) for b in EXP["bounds"]}
            scen["localized"] = local
            scen["localized_range"] = {
                str(b): [min(v[str(b)]["p"] for v in local.values()),
                         max(v[str(b)]["p"] for v in local.values())]
                for b in EXP["bounds"]
            }  # fmt: skip
            t["power"][str(bias)] = scen
        out["truths"][truth] = t
        print(f"{truth} done", flush=True)
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
