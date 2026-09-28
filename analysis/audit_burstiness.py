"""Audit of the burstiness statistic and fits (verification audit, 2026-09-28).

Usage: uv run python analysis/audit_burstiness.py [--split training]

Reports, for eligible hours of the chosen split (de-jittered timestamps):
  - per-hour fits of (sigma, tau) and their dependence on the hour's rate
  - a bootstrap over hours of the pooled fit
  - sensitivity of the pooled fit to the detrending window
  - alternative models fitted to the same six points (OU, two-timescale OU, power law)
  - estimator recovery on synthetic traffic with known parameters

Defaults to the training split. The holdout split can't be selected here.
"""

from __future__ import annotations

import argparse
import json

import numpy as np

from relay.traffic.burstiness import constant_modulation
from relay.traffic.stats import WINDOWS_S, fit_sigma_tau, ou_shape, rate_cv2

import common


def eligible(split: str) -> list[tuple[float, np.ndarray]]:
    out = []
    for arr in common.load_split(split).values():
        for _, th in common.hours(common.dejitter(arr["t"])):
            rate = len(th) / 3600
            if rate >= common.MIN_ELIGIBLE_RATE:
                out.append((rate, th))
    return out


def recovery(rate: float, sigma: float, tau: float, seeds: int = 6) -> dict[str, float]:
    ests = []
    for seed in range(seeds):
        rng = np.random.default_rng(seed)
        lam = rate * 0.1 * constant_modulation(sigma, tau, 36_000, 0.1, rng)
        bins = np.repeat(np.arange(36_000), rng.poisson(lam))
        t = np.sort((bins + rng.random(len(bins))) * 0.1)
        s, tt, _ = fit_sigma_tau(np.clip(rate_cv2(t, 3600), 1e-12, None))
        ests.append((s, tt))
    e = np.array(ests)
    return {"rate": rate, "sigma_mean": float(e[:, 0].mean()), "sigma_sd": float(e[:, 0].std()),
            "tau_mean": float(e[:, 1].mean()), "tau_sd": float(e[:, 1].std())}  # fmt: skip


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=("training", "validation"), default="training")
    args = parser.parse_args()
    hours = eligible(args.split)
    rates = np.array([r for r, _ in hours])
    curves = np.array([rate_cv2(th, 3600) for _, th in hours])
    pooled = np.median(curves, axis=0)
    sigma, tau, _ = fit_sigma_tau(pooled)
    per = np.array([fit_sigma_tau(np.clip(c, 1e-12, None))[:2] for c in curves])
    slope, intercept = np.polyfit(np.log(rates), np.log(per[:, 0]), 1)

    rng = np.random.default_rng(0)
    boot = np.array([fit_sigma_tau(np.median(curves[rng.integers(0, len(curves), len(curves))], axis=0))[:2]
                     for _ in range(200)])  # fmt: skip

    detrend = {}
    for k in (120, 300, 600, 1200, 1800, 3600):
        c = np.median([rate_cv2(th, 3600, k=k) for _, th in hours], axis=0)
        detrend[k] = fit_sigma_tau(np.clip(c, 1e-12, None))[:2]

    w = np.asarray(WINDOWS_S, dtype=float)
    best2 = None
    for t1 in np.geomspace(0.2, 30, 40):
        for t2 in np.geomspace(30, 3000, 40):
            g = np.vstack([ou_shape(w, t1), ou_shape(w, t2)]).T
            coef, *_ = np.linalg.lstsq(g, pooled, rcond=None)
            if (coef >= 0).all():
                e = float(np.sum((np.log(np.clip(g @ coef, 1e-12, None)) - np.log(pooled)) ** 2))
                if best2 is None or e < best2[0]:
                    best2 = (e, t1, t2)
    b, a = np.polyfit(np.log(w), 0.5 * np.log(pooled), 1)
    power_sse = float(np.sum((0.5 * np.log(pooled) - (a + b * np.log(w))) ** 2) * 4)

    report = {
        "split": args.split,
        "eligible_hours": len(hours),
        "pooled_fit": {"sigma": sigma, "tau_s": tau},
        "bootstrap_95ci": {"sigma": np.percentile(boot[:, 0], [2.5, 97.5]).tolist(),
                           "tau_s": np.percentile(boot[:, 1], [2.5, 97.5]).tolist()},
        "per_hour": {"sigma_median": float(np.median(per[:, 0])), "tau_median": float(np.median(per[:, 1])),
                     "log_sigma_vs_log_rate_slope": float(slope), "intercept": float(intercept)},
        "detrend_sensitivity": {str(k): {"sigma": v[0], "tau_s": v[1]} for k, v in detrend.items()},
        "alternative_models_log_sse": {"ou": fit_sigma_tau(pooled)[2],
                                       "two_timescale_ou": best2[0] if best2 else None,
                                       "power_law": power_sse},
        "estimator_recovery": [recovery(r, 0.16, 9.0) for r in (10, 80)],
    }  # fmt: skip
    print(json.dumps(report, indent=1, default=float))


if __name__ == "__main__":
    main()
