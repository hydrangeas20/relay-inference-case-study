"""Cycle 2 queue-validation rule, FROZEN (Cycle 2 preregistration, Amendment 1).

This is the only queue-validation path for Cycle 2 candidates. It implements the rule
audited in docs/validation/phase-2-cycle-2-criterion-audit.md (sections 6-7) at the
bound selected by the precommitted decision rule. Its content hash is recorded in
analysis/cycle2_validation_freeze.json; tests fail if this file changes.

The rule, per gating fold (Fri, Mon, Tue, Thu; 24 eligible hours each):

  inputs     per hour h, cell c in (s, rho) and metric k in (p95, p99): the model's
             median over 20 seeds (m), the Poisson control's median (p), and the
             Azure value (a)
  near zero  x is near zero if x < 0.01 * s (the frozen Cycle 1 definition)
  G          for each (c, k): exp(mean over informative hours of log(m / a)), where
             an hour is informative if neither m nor a is near zero; G = 1 when no
             hour is informative
  C1'        every G within [1 / B, B], B = 1.40 (inclusive)
  cap        one-sided near-zero hours (exactly one of m, a near zero), as a
             fraction of the fold's hour x cell x metric values, <= 0.10
  C3         criterion 3 exactly as frozen: queueing.judge_cell with the clarified
             rule; >= 80% of non-tie cells beat Poisson, with >= 1 non-tie cell
  fold pass  C1' and C3 and cap
  safety     a fold violates C2' if any G lies outside [0.5, 2.0] (inclusive)

  RULE       at least 3 of the 4 gating folds pass, AND no gating fold violates C2'

Not gates, by construction: the Azure-vs-Azure bootstrap (report-only; nothing here
accepts it) and Cycle 1's per-cell criteria 1-2 (rejected; never referenced here).

Resolution: this validator does not establish distributional equality or +/-10-15%
queue fidelity. See RESOLUTION_STATEMENT.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

import numpy as np

from relay.traffic.queueing import NEAR_ZERO, judge_cell

import cycle2_data

# ---- frozen constants (Amendment 1) ----------------------------------------------------
EQUIVALENCE_BOUND = 1.40
SAFETY_BOUNDS = (0.5, 2.0)
NEARZERO_CAP = 0.10
FOLDS_REQUIRED = 3
GATING_FOLDS = ("2024-05-10", "2024-05-13", "2024-05-14", "2024-05-16")  # Fri, Mon, Tue, Thu
HOURS_PER_FOLD = 24
SERVICE_TIMES_S = (0.2, 1.0)
UTILISATIONS = (0.6, 0.8)
CELLS = tuple((s, rho) for s in SERVICE_TIMES_S for rho in UTILISATIONS)
METRICS = ("p95", "p99")
CRITERION_3_RULE = "clarified"  # Cycle 1 Amendment 2, A2.3
CRITERION_3_MIN_FRACTION = 0.8
SEEDS_PER_CELL = 20
# Floating-point slack for the inclusive bounds (G is an exp-mean of logs).
_EPS = 1e-12

RESOLUTION_STATEMENT = (
    "This validator does not establish close distributional equality or +/-10-15% "
    "queue fidelity. Under the 200-replicate perfect-model audit at B = 1.40: biases "
    "of about 1.15x are generally not detected (8-13% global); about 1.25x have "
    "limited power (44-46% global); about 1.30x global biases are detected 71-73% of "
    "the time; 1.50x global bias is detected essentially always (100%); a 1.50x bias "
    "confined to one cell-and-percentile is detected 63-100% of the time depending on "
    "the cell. A passing candidate must not be described as 'matching Azure'. The "
    "supported reading is: 'No queue-behavior discrepancy was detected at the "
    "resolution supported by the preregistered validation procedure.'"
)


def _near_zero(x: np.ndarray, s: np.ndarray) -> np.ndarray:
    result: np.ndarray = x < NEAR_ZERO * s
    return result


def _as_array(hours: list[list[Mapping[str, float]]]) -> np.ndarray:
    """[hour][cell] -> {metric: value}  as an array (hours, cells, metrics)."""
    return np.array([[[cell[k] for k in METRICS] for cell in hour] for hour in hours], dtype=float)


def fold_result(
    model: np.ndarray, poisson: np.ndarray, azure: np.ndarray, bound: float = EQUIVALENCE_BOUND
) -> dict[str, Any]:
    """One gating fold. Arrays are (hours, cells, metrics), cells and metrics in frozen order."""
    if model.shape != azure.shape or poisson.shape != azure.shape:
        raise ValueError("model, poisson and azure must have the same shape")
    if model.shape[1:] != (len(CELLS), len(METRICS)):
        raise ValueError(f"expected (hours, {len(CELLS)}, {len(METRICS)}), got {model.shape}")
    s = np.array([c[0] for c in CELLS])[None, :, None]
    low_m, low_a = _near_zero(model, s), _near_zero(azure, s)
    informative = ~low_m & ~low_a
    with np.errstate(divide="ignore", invalid="ignore"):
        log_r = np.where(informative, np.log(model / azure), 0.0)
    n_inf = informative.sum(axis=0)
    log_g = np.where(n_inf > 0, log_r.sum(axis=0) / np.maximum(n_inf, 1), 0.0)
    g = np.exp(log_g)
    c1p = bool(np.all(np.abs(log_g) <= math.log(bound) + _EPS))
    lo, hi = SAFETY_BOUNDS
    safety_violation = bool(
        np.any(log_g < math.log(lo) - _EPS) or np.any(log_g > math.log(hi) + _EPS)
    )
    onesided = float((low_m ^ low_a).mean())
    cap_ok = onesided <= NEARZERO_CAP + _EPS
    beats = non_tie = 0
    for h in range(model.shape[0]):
        for i, (svc, _rho) in enumerate(CELLS):
            m = dict(zip(METRICS, model[h, i], strict=True))
            p = dict(zip(METRICS, poisson[h, i], strict=True))
            a = dict(zip(METRICS, azure[h, i], strict=True))
            v = judge_cell(m, p, a, svc, CRITERION_3_RULE).beats_poisson
            if v is not None:
                non_tie += 1
                beats += bool(v)
    c3 = non_tie > 0 and beats >= CRITERION_3_MIN_FRACTION * non_tie
    return {
        "G": {
            f"s{c[0]}_rho{c[1]}_{k}": float(g[i, j])
            for i, c in enumerate(CELLS)
            for j, k in enumerate(METRICS)
        },  # fmt: skip
        "C1_prime": c1p,
        "criterion_3": bool(c3),
        "criterion_3_beats_fraction": beats / max(1, non_tie),
        "onesided_nearzero_fraction": onesided,
        "nearzero_cap_ok": bool(cap_ok),
        "safety_violation": safety_violation,
        "passed": bool(c1p and c3 and cap_ok),
    }


def rule(folds: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """The frozen 3-of-4 rule over exactly the four gating folds."""
    if set(folds) != set(GATING_FOLDS):
        raise ValueError(f"need exactly the gating folds {GATING_FOLDS}, got {sorted(folds)}")
    passing = [d for d in GATING_FOLDS if folds[d]["passed"]]
    unsafe = [d for d in GATING_FOLDS if folds[d]["safety_violation"]]
    return {
        "folds_passing": passing,
        "folds_with_safety_violation": unsafe,
        "passed": len(passing) >= FOLDS_REQUIRED and not unsafe,
        "resolution_statement": RESOLUTION_STATEMENT,
    }


def validate(
    folds: Mapping[str, Mapping[str, list[list[Mapping[str, float]]]]],
) -> dict[str, Any]:
    """Validate a candidate from per-fold queue metrics.

    folds[day] = {"model": hours x cells, "poisson": ..., "azure": ...}, each cell a
    {"p95", "p99"} mapping. Enters Cycle 2 cache-only mode first (fail-closed), so no
    code path reached from here can touch the raw trace.
    """
    cycle2_data.enter_cycle2_mode()
    results = {}
    for day in GATING_FOLDS:
        f = folds[day]
        arrays = [_as_array(f[k]) for k in ("model", "poisson", "azure")]
        if arrays[0].shape[0] != HOURS_PER_FOLD:
            raise ValueError(f"{day}: expected {HOURS_PER_FOLD} hours, got {arrays[0].shape[0]}")
        results[day] = fold_result(*arrays)
    return {"folds": results, **rule(results)}
