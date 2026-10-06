"""Bounded Nelder-Mead with a hard evaluation budget (Cycle 2 Amendment 3, A3.2-A3.4).

No candidate model here: `fit` takes any objective of the transformed parameters.

Procedure, frozen by A3.3:
  - evaluate the 8 starts (counted in the budget);
  - pick the lowest-objective start (ties: lower start number); if none is finite,
    the fit is invalid;
  - run Nelder-Mead from that start only: reflection 1, expansion 2, contraction
    0.5, shrink 0.5; initial simplex = start plus one vertex per coordinate moved by
    10% of that coordinate's bound width (towards the upper bound, or the lower if
    that would exceed it); trial points clipped to the bounds;
  - stop when max f - min f <= 1e-4 and the largest coordinate spread <= 1e-4, or
    when the total budget (300, starts included) is spent;
  - the result is the best finite point among ALL evaluations.
Invalid evaluations (non-finite, or an exception) count as +inf and are recorded.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from typing import Any

import numpy as np

BUDGET = 300
STARTS = 8
REFLECT, EXPAND, CONTRACT, SHRINK = 1.0, 2.0, 0.5, 0.5
SIMPLEX_STEP_FRACTION = 0.10
FTOL = 1e-4
XTOL = 1e-4
# Starts 1-7 in the unit cube (A3.2): centre, then axial points at 0.1 / 0.9.
UNIT_DESIGN: tuple[tuple[float, float, float], ...] = (
    (0.5, 0.5, 0.5),
    (0.1, 0.5, 0.5),
    (0.9, 0.5, 0.5),
    (0.5, 0.1, 0.5),
    (0.5, 0.9, 0.5),
    (0.5, 0.5, 0.1),
    (0.5, 0.5, 0.9),
)


def to_theta(a: float, b: float, tau: float) -> np.ndarray:
    return np.array([math.log(a), b, math.log(tau)])


def from_theta(theta: Sequence[float]) -> dict[str, float]:
    return {"a": math.exp(theta[0]), "b": float(theta[1]), "tau_s": math.exp(theta[2])}


def starts(lower: np.ndarray, upper: np.ndarray, cycle1_theta: np.ndarray) -> list[np.ndarray]:
    """The eight frozen starts: the unit design mapped to the bounds, then Cycle 1's fit."""
    lower, upper = np.asarray(lower, float), np.asarray(upper, float)
    if not np.all(lower < upper):
        raise ValueError("each lower bound must be below its upper bound")
    if not (np.all(cycle1_theta >= lower) and np.all(cycle1_theta <= upper)):
        raise ValueError("the bounds must contain the Cycle 1 fit (start 8)")
    out = [lower + np.array(u) * (upper - lower) for u in UNIT_DESIGN]
    return [*out, np.asarray(cycle1_theta, float)]


class _Counter:
    def __init__(self, f: Callable[[np.ndarray], float], budget: int) -> None:
        self.f, self.budget = f, budget
        self.history: list[dict[str, Any]] = []

    @property
    def remaining(self) -> int:
        return self.budget - len(self.history)

    def __call__(self, x: np.ndarray, phase: str) -> float:
        if self.remaining <= 0:
            raise _BudgetExhausted
        try:
            value = float(self.f(x))
            error = None
        except Exception as exc:  # noqa: BLE001 - any failure is an invalid evaluation
            value, error = math.inf, f"{type(exc).__name__}: {exc}"
        if not math.isfinite(value):
            value = math.inf
        self.history.append({"theta": [float(v) for v in x], "f": value, "phase": phase,
                             "error": error})  # fmt: skip
        return value


class _BudgetExhausted(Exception):
    pass


def _nelder_mead(
    ev: _Counter, x0: np.ndarray, f0: float, lower: np.ndarray, upper: np.ndarray
) -> str:
    n = len(x0)
    width = upper - lower
    simplex = [x0.copy()]
    values = [f0]
    for i in range(n):
        step = SIMPLEX_STEP_FRACTION * width[i]
        x = x0.copy()
        x[i] = x[i] + step if x[i] + step <= upper[i] else x[i] - step
        simplex.append(np.clip(x, lower, upper))
        values.append(ev(simplex[-1], "simplex"))
    while True:
        order = np.argsort(values, kind="stable")
        simplex = [simplex[i] for i in order]
        values = [values[i] for i in order]
        spread = max(float(np.max(np.abs(x - simplex[0]))) for x in simplex[1:])
        if values[-1] - values[0] <= FTOL and spread <= XTOL:
            return "converged"
        centroid = np.mean(simplex[:-1], axis=0)
        xr = np.clip(centroid + REFLECT * (centroid - simplex[-1]), lower, upper)
        fr = ev(xr, "reflect")
        if fr < values[0]:
            xe = np.clip(centroid + EXPAND * (xr - centroid), lower, upper)
            fe = ev(xe, "expand")
            simplex[-1], values[-1] = (xe, fe) if fe < fr else (xr, fr)
            continue
        if fr < values[-2]:
            simplex[-1], values[-1] = xr, fr
            continue
        if fr < values[-1]:
            xc = np.clip(centroid + CONTRACT * (xr - centroid), lower, upper)
            fc = ev(xc, "contract_out")
            if fc <= fr:
                simplex[-1], values[-1] = xc, fc
                continue
        else:
            xc = np.clip(centroid + CONTRACT * (simplex[-1] - centroid), lower, upper)
            fc = ev(xc, "contract_in")
            if fc < values[-1]:
                simplex[-1], values[-1] = xc, fc
                continue
        for i in range(1, len(simplex)):
            simplex[i] = np.clip(simplex[0] + SHRINK * (simplex[i] - simplex[0]), lower, upper)
            values[i] = ev(simplex[i], "shrink")


def fit(
    objective: Callable[[np.ndarray], float],
    lower: np.ndarray,
    upper: np.ndarray,
    start_points: list[np.ndarray],
    budget: int = BUDGET,
) -> dict[str, Any]:
    """The frozen procedure. Returns the best point, its validity and the full history."""
    lower, upper = np.asarray(lower, float), np.asarray(upper, float)
    if len(start_points) != STARTS:
        raise ValueError(f"need exactly {STARTS} starts")
    ev = _Counter(objective, budget)
    start_values = [ev(np.asarray(s, float), f"start_{i + 1}") for i, s in enumerate(start_points)]
    finite = [i for i, v in enumerate(start_values) if math.isfinite(v)]
    termination = "no_finite_start"
    chosen = None
    if finite:
        chosen = min(finite, key=lambda i: (start_values[i], i))
        try:
            termination = _nelder_mead(
                ev, np.asarray(start_points[chosen], float), start_values[chosen], lower, upper
            )
        except _BudgetExhausted:
            termination = "budget_exhausted"
    best = min((h for h in ev.history if math.isfinite(h["f"])), key=lambda h: h["f"], default=None)
    valid = best is not None and bool(
        np.all(np.array(best["theta"]) >= lower) and np.all(np.array(best["theta"]) <= upper)
    )
    return {
        "valid": valid,
        "termination": termination,
        "chosen_start": None if chosen is None else chosen + 1,
        "start_values": start_values,
        "best_theta": None if best is None else best["theta"],
        "best_params": None if best is None else from_theta(best["theta"]),
        "best_objective": None if best is None else best["f"],
        "evaluations": len(ev.history),
        "invalid_evaluations": sum(1 for h in ev.history if not math.isfinite(h["f"])),
        "history": ev.history,
    }
