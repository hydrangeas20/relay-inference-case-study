"""Analysis of the criterion-audit null for a PROPOSED aggregated criterion.

Usage: uv run python analysis/cycle2_null_aggregate.py

Reads only analysis/results/cycle2/criterion-audit.json (no Azure data, no
candidate). Written AFTER the audit result was seen, to support a prospective
criterion revision justified solely by the null (owner decision Q4). Nothing here
is adopted until reviewed and committed as a preregistration amendment.

Proposed fold statistic: for each queue cell (s, rho) and metric (p95, p99),
G = exp(mean over informative hours of log(model / reference)), the geometric-mean
ratio over the fold's hours. Hours where both are near zero (< 0.01 s) are
non-informative; one-sided near-zero hours are counted separately.

Power is measured by multiplying the null model's medians by a known factor:
synthetic, candidate-independent.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np

IN = Path("analysis/results/cycle2/criterion-audit.json")
OUT = Path("analysis/results/cycle2/criterion-audit-aggregate.json")
CELLS = [(0.2, 0.6), (0.2, 0.8), (1.0, 0.6), (1.0, 0.8)]
BOUNDS = (1.15, 1.2, 1.25, 1.3, 1.35, 1.4)
SAFETY = 2.0
BIASES: dict[str, Callable[[int], float]] = {
    "none": lambda i: 1.0,
    "x1.15 all cells": lambda i: 1.15,
    "x1.25 all cells": lambda i: 1.25,
    "x1.5 all cells": lambda i: 1.5,
    "x0.67 all cells": lambda i: 0.67,
    "x1.3 at rho 0.8 only": lambda i: 1.3 if i in (1, 3) else 1.0,
    "x1.5 at s 1.0, rho 0.8 only": lambda i: 1.5 if i == 3 else 1.0,
}


def fold_g(
    hours: list[dict[str, Any]],
    model_of: Callable[[dict[str, Any]], list[dict[str, float]]],
    ref_of: Callable[[dict[str, Any]], list[dict[str, float]]],
    bias: Callable[[int], float],
) -> tuple[dict[str, float], float]:
    g, onesided, cells = {}, 0, 0
    for i, (s, rho) in enumerate(CELLS):
        for k in ("p95", "p99"):
            logs = []
            for h in hours:
                m, a, thr = model_of(h)[i][k] * bias(i), ref_of(h)[i][k], 0.01 * s
                cells += 1
                if a < thr and m < thr:
                    continue
                if a < thr or m < thr:
                    onesided += 1
                    continue
                logs.append(np.log(m / a))
            g[f"s{s}_rho{rho}_{k}"] = float(np.exp(np.mean(logs))) if logs else 1.0
    return g, onesided / cells


def main() -> None:
    d = json.loads(IN.read_text())
    folds = d["folds"]
    reps = len(folds[0]["hours"][0]["cycle1_C1"]["references"])
    out: dict[str, Any] = {"source": str(IN), "replicates": reps, "bounds": BOUNDS, "null": {}}
    for truth in ("cycle1_C1", "bootstrap"):
        table: dict[str, Any] = {}
        for label, bias in BIASES.items():
            max_log = np.zeros((reps, len(folds)))
            onesided = np.zeros((reps, len(folds)))
            for r in range(reps):
                for fi, f in enumerate(folds):
                    g, o = fold_g(f["hours"], lambda h, t=truth: h[t]["model"],
                                  lambda h, t=truth, r=r: h[t]["references"][r], bias)  # fmt: skip
                    max_log[r, fi] = max(abs(np.log(v)) for v in g.values())
                    onesided[r, fi] = o
            table[label] = {
                "max_factor_quantiles_50_80_90_95_99": np.exp(
                    np.percentile(max_log, [50, 80, 90, 95, 99])
                ).round(3).tolist(),
                "P_fold_pass": {str(b): float((max_log <= np.log(b)).mean()) for b in BOUNDS},
                "P_rule_3_of_4": {
                    str(b): float(((max_log <= np.log(b)).sum(1) >= 3).mean()) for b in BOUNDS
                },
                "P_fold_safety_violation_beyond_2x": float((max_log > np.log(SAFETY)).mean()),
                "onesided_nearzero_fraction_mean_max": [float(onesided.mean()), float(onesided.max())],
            }  # fmt: skip
        out["null"][truth] = table
    n2 = {}
    for f in folds:
        g, o = fold_g(
            f["hours"], lambda h: h["bootstrap"]["model"], lambda h: h["azure"], BIASES["none"]
        )
        n2[f["weekday"]] = {"G": {k: round(v, 3) for k, v in g.items()},
                            "max_factor": round(float(max(max(v, 1 / v) for v in g.values())), 3),
                            "onesided_fraction": round(o, 4)}  # fmt: skip
    out["N2_azure_vs_bootstrap"] = n2
    sup = [h["bootstrap_superposed_fraction"] for f in folds for h in f["hours"]]
    out["bootstrap_superposed_fraction_mean"] = float(np.mean(sup))
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
