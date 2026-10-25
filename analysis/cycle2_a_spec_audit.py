"""Candidate-independent specification audit for proposed Candidate A (no data, no A model).

Usage: uv run python analysis/cycle2_a_spec_audit.py

Writes analysis/results/cycle2/a-spec-audit.json. Everything here is analytical or
synthetic: no Azure data is read, no Candidate A model is built, fitted or simulated,
and no traffic or queue is generated.

1. Link: the proposed delta = 1 sinh-arcsinh multiplier
   M~ = 1 + sigma * (sinh(asinh(Z) + xi) - mu(xi)) / s(xi),  Z ~ N(0, 1),
   with closed-form mu, s; and the clipped M = max(M~, 0.02). Moments of M come from
   exact 1-D integrals over Z (trapezoid on a 4,000,001-point grid over [-40, 40]),
   checked against 2e7-draw Monte Carlo. Also the Gaussian-copula correlation transfer
   corr(h(Y1), h(Y2)) as a function of corr(Y1, Y2), by Hermite expansion (unclipped).
2. Optimiser: the frozen analysis/cycle2_optimizer.fit, unchanged, on synthetic
   objectives in the unit box for n = 3, 6, 7 (sphere, rotated quadratics with condition
   numbers 1e2 and 1e4, a banana valley). Scaled like D's loss (minimum 700, ~10^4
   across the box); 8 starts (Hadamard rows + one interior point); 20 replicates each.
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
from numpy.polynomial import hermite_e

import cycle2_optimizer as opt

OUT = Path("analysis/results/cycle2/a-spec-audit.json")
CLIP = 0.02
_Z = np.linspace(-40.0, 40.0, 4_000_001)
_PHI = np.exp(-_Z * _Z / 2) / math.sqrt(2 * math.pi)
K = float(np.trapezoid(np.sqrt(1 + _Z * _Z) * _PHI, _Z))  # E sqrt(1 + Z^2)


def mu(xi: float) -> float:
    return K * math.sinh(xi)


def s(xi: float) -> float:
    return math.sqrt(math.cosh(xi) ** 2 + 2 * math.sinh(xi) ** 2 - (K * math.sinh(xi)) ** 2)


def clipped_moments(sigma: float, xi: float) -> dict[str, float]:
    mt = 1 + sigma * (np.sinh(np.arcsinh(_Z) + xi) - mu(xi)) / s(xi)
    m = np.maximum(mt, CLIP)
    em, em2 = (float(np.trapezoid(v * _PHI, _Z)) for v in (m, m * m))
    emt, emt2 = (float(np.trapezoid(v * _PHI, _Z)) for v in (mt, mt * mt))
    x_star = mu(xi) + s(xi) * (CLIP - 1) / sigma  # M~ < CLIP  <=>  X < x_star
    z_star = math.sinh(math.asinh(x_star) - xi)
    return {"sigma": sigma, "xi": xi, "p_clip": 0.5 * (1 + math.erf(z_star / math.sqrt(2))),
            "mean_unclipped": emt, "sd_unclipped_over_sigma": math.sqrt(emt2 - emt**2) / sigma,
            "mean": em, "mean_shift": em - 1, "sd_over_sigma": math.sqrt(em2 - em * em) / sigma}  # fmt: skip


def sigma_at_clip_probability(p: float, xi: float) -> float:
    lo, hi = 1e-3, 50.0
    for _ in range(100):
        mid = math.sqrt(lo * hi)
        lo, hi = (mid, hi) if clipped_moments(mid, xi)["p_clip"] < p else (lo, mid)
    return math.sqrt(lo * hi)


def link_audit() -> dict[str, Any]:
    closed = []
    for xi in (-2.0, -1.0, -0.5, 0.0, 0.5, 1.0, 2.0):
        x = np.sinh(np.arcsinh(_Z) + xi)
        m = float(np.trapezoid(x * _PHI, _Z))
        sd = math.sqrt(float(np.trapezoid(x * x * _PHI, _Z)) - m * m)
        sk = float(np.trapezoid(((x - m) / sd) ** 3 * _PHI, _Z))
        closed.append({"xi": xi, "mu_closed": mu(xi), "mu_numeric": m, "s_closed": s(xi),
                       "s_numeric": sd, "skewness": sk})  # fmt: skip
    grid = [clipped_moments(sg, xi) for sg in (0.1, 0.2, 0.3, 0.4, 0.5, 0.7, 1.0, 2.0)
            for xi in (-2.0, -1.0, -0.5, 0.0, 0.5, 1.0, 2.0)]  # fmt: skip
    fa4 = [clipped_moments(sigma_at_clip_probability(1e-3, xi), xi)
           for xi in (-2.0, -1.0, -0.5, 0.0, 0.5, 1.0, 2.0)]  # fmt: skip
    rng = np.random.default_rng(20261008)
    z = rng.standard_normal(20_000_000)
    mc = []
    for sg, xi in ((0.3, 0.0), (0.3, -1.0), (0.5, 0.0), (0.5, 0.5), (1.0, 1.0), (0.2, -2.0)):
        mt = 1 + sg * (np.sinh(np.arcsinh(z) + xi) - mu(xi)) / s(xi)
        m = np.maximum(mt, CLIP)
        mc.append({"sigma": sg, "xi": xi, "n": len(z), "mean_unclipped": float(mt.mean()),
                   "sd_unclipped_over_sigma": float(mt.std() / sg), "mean": float(m.mean()),
                   "sd_over_sigma": float(m.std() / sg), "p_clip": float((mt < CLIP).mean()),
                   "quadrature": clipped_moments(sg, xi)})  # fmt: skip
    x, w = hermite_e.hermegauss(200)
    w = w / w.sum()
    fact = [math.factorial(k) for k in range(41)]
    transfer = []
    for xi in (0.0, 0.25, 0.5, 1.0, 2.0):
        h = np.sinh(np.arcsinh(x) + xi)
        c = [
            float((w * h * hermite_e.hermeval(x, [0] * k + [1])).sum()) / fact[k] for k in range(41)
        ]
        var = sum(c[k] ** 2 * fact[k] for k in range(1, 41))
        row: dict[str, float] = {"xi": xi}
        for rho in (0.1, 0.3, 0.5, 0.8, 0.95):
            row[f"rho_{rho}"] = sum(c[k] ** 2 * fact[k] * rho**k for k in range(1, 41)) / var
        transfer.append(row)
    return {"K": K, "closed_form_check": closed, "clipping_grid": grid,
            "at_single_bin_clip_probability_0.001": fa4, "monte_carlo_check": mc,
            "copula_correlation_transfer_unclipped": transfer}  # fmt: skip


_H = np.array([[(-1) ** bin(i & j).count("1") for j in range(8)] for i in range(8)])


def _starts(n: int) -> list[np.ndarray]:
    return [np.array(0.5 + 0.3 * _H[r, 1 : 1 + n], float) for r in range(1, 8)] + [np.full(n, 0.4)]


def _objective(
    kind: str, n: int, rng: np.random.Generator
) -> tuple[Callable[[np.ndarray], float], np.ndarray]:
    xs = rng.uniform(0.2, 0.8, n)
    q, _ = np.linalg.qr(rng.standard_normal((n, n)))
    cond = {"sphere": 0.0, "cond1e2": 2.0, "cond1e4": 4.0}.get(kind, 0.0)
    a = q @ np.diag(np.logspace(0, cond, n) / 10 ** (cond / 2)) @ q.T

    def f(x: np.ndarray) -> float:
        d = np.asarray(x, float) - xs
        if kind == "banana":
            y = 4 * d
            return 700.0 + 50.0 * sum(
                100 * (y[i + 1] - y[i] ** 2) ** 2 + y[i] ** 2 for i in range(n - 1)
            )
        return 700.0 + 40000.0 * float(d @ a @ d)

    return f, xs


def optimizer_audit() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for kind in ("sphere", "cond1e2", "cond1e4", "banana"):
        for n in (3, 6, 7):
            rng = np.random.default_rng(1000 + n)
            recs = []
            for _ in range(20):
                f, xs = _objective(kind, n, rng)
                r = opt.fit(f, np.zeros(n), np.ones(n), _starts(n))
                recs.append({"termination": r["termination"], "evaluations": r["evaluations"],
                             "excess": r["best_objective"] - 700.0,
                             "distance": float(np.linalg.norm(np.array(r["best_theta"]) - xs))})  # fmt: skip
            conv = [x for x in recs if x["termination"] == "converged"]
            out[f"{kind}_n{n}"] = {
                "replicates": len(recs),
                "converged_fraction": len(conv) / len(recs),
                "evaluations_median_if_converged": float(np.median([x["evaluations"] for x in conv])) if conv else None,
                "excess_median": float(np.median([x["excess"] for x in recs])),
                "excess_max": float(np.max([x["excess"] for x in recs])),
                "distance_median": float(np.median([x["distance"] for x in recs])),
                "distance_max": float(np.max([x["distance"] for x in recs])),
            }  # fmt: skip
    return out


def main() -> None:
    record = {"scope": "candidate-independent: analytical and synthetic only; no Azure data, "
              "no Candidate A model, fit, simulation or queue",
              "link": link_audit(), "optimizer": optimizer_audit()}  # fmt: skip
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(record, indent=1) + "\n")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
