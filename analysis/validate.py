"""Preregistered candidate validation (docs/validation/phase-2-preregistration.md §6, §7, §11).

Usage:
  uv run python analysis/validate.py                 # Thursday: both candidates + selection
  uv run python analysis/validate.py --holdout C1    # Wednesday, ONCE, selected candidate only,
                                                     # after explicit written authorisation

Refuses to run while preregistration open items are unresolved. Writes
analysis/results/validation-<split>.json with every number behind every verdict.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np

from relay.traffic.burstiness import BurstinessModel, load_candidate
from relay.traffic.generate import BIN_S, cox_arrivals
from relay.traffic.queueing import (
    CellVerdict,
    accept,
    as_dict,
    judge_cell,
    queue_metrics,
    servers_for,
)
from relay.traffic.stats import (
    WINDOWS_S,
    moving_average_trend,
    ou_shape,
    per_second_counts,
    rate_cv2,
)

import common
import validation_config as cfg

REFERENCE = Path("traffic/reference/azure_code_burstiness.json")
RESULTS = Path("analysis/results")


def predicted_cv(model: BurstinessModel, rates: list[float]) -> np.ndarray:
    w = np.asarray(WINDOWS_S, dtype=float)
    lam = np.asarray(rates)
    sig = model.sigma(lam, "edge")
    tau = model.tau(lam)
    cv2 = [s * s * ou_shape(w, t) for s, t in zip(sig, tau, strict=True)]
    return np.sqrt(np.median(np.array(cv2), axis=0))


def observed_cv(hours: list[dict[str, Any]]) -> np.ndarray:
    return np.sqrt(np.clip(np.median([h["cv2"] for h in hours], axis=0), 0, None))


def band_check(pred: np.ndarray, obs: np.ndarray, tol: float) -> dict[str, Any]:
    err = pred - obs
    same_sign = bool(np.all(err > 0) or np.all(err < 0))
    magnitude_ok = bool(np.max(np.abs(err)) <= tol)
    passed = magnitude_ok and not (cfg.O1_SIGN_CLAUSE == "pass/fail" and same_sign)
    out: dict[str, Any] = {"tolerance": tol, "predicted": pred.round(5).tolist(),
                           "observed": obs.round(5).tolist(), "error": err.round(5).tolist(),
                           "max_abs_error": round(float(np.max(np.abs(err))), 5),
                           "magnitude_ok": magnitude_ok, "passed": passed}  # fmt: skip
    if cfg.O1_SIGN_CLAUSE in ("pass/fail", "diagnostic"):
        out["all_same_sign"] = same_sign
    return out


def hour_rows(split: str, allow_holdout: bool) -> list[dict[str, Any]]:
    rows = []
    for day, arr in common.load_split(split, allow_holdout=allow_holdout).items():
        t = common.dejitter(arr["t"])
        for h, th in common.hours(t):
            rate = len(th) / 3600
            if rate >= common.MIN_ELIGIBLE_RATE and common.band_of(rate) is not None:
                rows.append({"day": common.DAYS[day], "hour": h, "rate": rate, "times": th,
                             "cv2": rate_cv2(th, 3600)})  # fmt: skip
    return rows


def out_of_sample(model: BurstinessModel, rows: list[dict[str, Any]]) -> dict[str, Any]:
    checks = {}
    for label, (lo, hi), tol in cfg.check_bands():
        hs = [r for r in rows if lo <= r["rate"] < hi]
        if hs:
            checks[label] = {"hours": len(hs), **band_check(predicted_cv(model, [h["rate"] for h in hs]), observed_cv(hs), tol)}  # fmt: skip
    return {"bands": checks, "passed": all(c["passed"] for c in checks.values())}


def band_holdouts(
    reference: dict[str, Any], name: str, train: list[dict[str, Any]]
) -> dict[str, Any]:
    out = {}
    for b, (lo, hi) in enumerate(common.RATE_BANDS):
        key = f"without {lo:g}-{hi:g}"
        fit = reference["band_holdout_fits"][key][name]
        model = BurstinessModel(name=f"{name}-{key}", a=fit["a"], b=fit["b"],
                                band_rates=tuple(fit["band_rates"]), band_taus=tuple(fit["band_taus"]),
                                rate_min=reference["observed_range_rps"][0],
                                rate_max=reference["observed_range_rps"][1])  # fmt: skip
        hs = [r for r in train if lo <= r["rate"] < hi]
        tol = next(t for label, (l2, h2), t in cfg.check_bands() if l2 <= lo and hi <= h2)
        res = band_check(predicted_cv(model, [h["rate"] for h in hs]), observed_cv(hs), tol)
        role = "interpolation" if b in cfg.INTERPOLATION_HOLDOUTS else "extrapolation"
        out[f"{lo:g}-{hi:g}"] = {"role": role, "hours": len(hs), **res}
    passed = all(v["passed"] for v in out.values() if v["role"] == "interpolation")
    return {"bands": out, "interpolation_passed": passed}


def queueing(models: dict[str, BurstinessModel], rows: list[dict[str, Any]]) -> dict[str, Any]:
    cells: dict[str, list[dict[str, Any]]] = {name: [] for name in models}
    for r in rows:
        h, times = r["hour"], r["times"]
        trend = moving_average_trend(per_second_counts(times, 3600))
        lam = np.repeat(trend, int(round(1 / BIN_S)))
        runs: dict[str, list[np.ndarray]] = {name: [] for name in models}
        pois: list[np.ndarray] = []
        for seed in cfg.SEEDS:
            for name, m in models.items():
                rng = np.random.default_rng(cfg.MODEL_SEED_BASE * h + seed)
                runs[name].append(
                    cox_arrivals(SimpleNamespace(burstiness=m), lam, rng, "edge", 3600.0)
                )  # type: ignore[arg-type]
            prng = np.random.default_rng(cfg.POISSON_SEED_OFFSET + cfg.MODEL_SEED_BASE * h + seed)
            zero = BurstinessModel("poisson", 0.0, 0.0, (1.0,), (1.0,), 0.0, 1e12)
            pois.append(cox_arrivals(SimpleNamespace(burstiness=zero), lam, prng, "edge", 3600.0))  # type: ignore[arg-type]
        for s in cfg.SERVICE_TIMES_S:
            for rho in cfg.UTILISATIONS:
                c = servers_for(r["rate"], s, rho)
                az = as_dict(queue_metrics(times, c, s, 3600.0))
                pm = _median_metrics([queue_metrics(t, c, s, 3600.0) for t in pois])
                for name in models:
                    mm = _median_metrics([queue_metrics(t, c, s, 3600.0) for t in runs[name]])
                    v: CellVerdict = judge_cell(mm, pm, az, s)
                    cells[name].append({"day": r["day"], "hour": h, "rate": round(r["rate"], 3),
                                        "service_s": s, "target_rho": rho, "servers": c,
                                        "azure": az, "model": mm, "poisson": pm, "verdict": as_dict(v)})  # fmt: skip
    out = {}
    for name, cs in cells.items():
        verdicts = [CellVerdict(**c["verdict"]) for c in cs]
        out[name] = {"acceptance": as_dict(accept(verdicts)), "cells": cs}
    return out


def _median_metrics(ms: list[Any]) -> dict[str, float]:
    keys = (
        "p50",
        "p95",
        "p99",
        "fraction_waiting",
        "peak_waiting",
        "worst_60s_mean_wait",
        "utilisation",
    )
    return {k: float(np.median([getattr(m, k) for m in ms])) for k in keys}


def select(results: dict[str, Any]) -> dict[str, Any]:
    passing = [n for n in ("C1", "C2") if results[n]["passed_all"]]
    if len(passing) == 2:
        return {"selected": "C1", "rule": "both passed: C1 (fewer parameters)"}
    if len(passing) == 1:
        return {"selected": passing[0], "rule": "only this candidate passed"}
    frac = {n: results[n]["queueing"]["acceptance"]["in_band"] / max(1, results[n]["queueing"]["acceptance"]["cells"]) for n in ("C1", "C2")}  # fmt: skip
    choice = max(frac, key=lambda n: (frac[n], n == "C1"))
    return {"selected": choice, "provisional": True,
            "rule": "no candidate passed on Thursday; provisional choice by criterion-1 fraction",
            "criterion_1_fraction": frac}  # fmt: skip


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--holdout", choices=("C1", "C2"),
                        help="evaluate the Wednesday holdout ONCE with the selected candidate")  # fmt: skip
    args = parser.parse_args()
    cfg.require_resolved()
    reference = json.loads(REFERENCE.read_text())
    split = "holdout" if args.holdout else "validation"
    names = [args.holdout] if args.holdout else ["C1", "C2"]
    out_path = RESULTS / f"validation-{split}.json"
    if args.holdout and out_path.exists():
        sys.exit(f"{out_path} exists: the holdout is evaluated exactly once (preregistration §12)")

    rows = hour_rows(split, allow_holdout=bool(args.holdout))
    models = {n: load_candidate(reference, n) for n in names}
    results: dict[str, Any] = {n: {} for n in names}
    if not args.holdout:
        train = hour_rows("training", allow_holdout=False)
        for n in names:
            results[n]["band_holdouts"] = band_holdouts(reference, n, train)
    q = queueing(models, rows)
    for n, m in models.items():
        results[n]["out_of_sample"] = out_of_sample(m, rows)
        results[n]["queueing"] = q[n]
        results[n]["passed_all"] = (
            results[n]["out_of_sample"]["passed"]
            and results[n]["queueing"]["acceptance"]["passed"]
            and results[n].get("band_holdouts", {}).get("interpolation_passed", True)
        )
    record = {
        "split": split,
        "days": sorted({r["day"] for r in rows}),
        "hours": len(rows),
        "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "raw_sha256": common.RAW_SHA256,
        "reference_sha256": common.sha256_file(REFERENCE),
        "preregistration": {"O1": cfg.O1_SIGN_CLAUSE, "O2": cfg.O2_HIGH_BAND_TOLERANCE},
        "results": results,
    }
    if not args.holdout:
        record["selection"] = select(results)
    RESULTS.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(record, indent=1, default=float) + "\n")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
