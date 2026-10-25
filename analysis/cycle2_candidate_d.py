"""Candidate D (variant D1): the Cycle 1 single-timescale lognormal OU family, Cycle 2 procedure.

Usage:
  uv run python analysis/cycle2_candidate_d.py fit        # the 11 frozen fits
  uv run python analysis/cycle2_candidate_d.py evaluate   # queue validation + reports

Authorised by the owner on 2026-10-08. Every setting comes from the frozen Cycle 2
preregistration (Amendments 1-3 and their addenda). Nothing here is tuned.

Model (section 3, D1). The generator is the shipped one, unchanged:
relay.traffic.generate.cox_arrivals with relay.traffic.burstiness.BurstinessModel.
N_k ~ Poisson(lambda_k M_k dt), dt = 0.1 s, M = exp(sX - s^2/2), s^2 = ln(1 + sigma^2),
X one unit-variance OU process with a single tau, sigma(lambda) = a lambda^b. Out of
the frozen range (A3.8) only sigma extrapolates, by the same power law (scenario
"trend"); tau is a single constant. Three parameters; no others.

Fits (A3.2-A3.5; optimiser in cycle2_optimizer, frozen):
  all                    six development days (in-sample report; Wednesday model)
  <day> (x6)             leave-one-day-out: the five other days
  without-band-<b> (x4)  six days, band b's hours left out of the loss (A3.9)

Validation (A3.9): each held-out day's eligible hours simulated on their own trend
with that fold's fit; per (hour, cell) the median p95/p99 over 20 seeds for D and for
the Poisson control (A3.6 namespaces); Azure's own value; gating folds through the
frozen cycle2_validation.validate. Sat and Sun are reported with the same fold
computation but don't gate.

Implementation readings fixed here before any D result (recorded in the ledger):
  R1  The simulated band-pooled value pools the band's simulated hour-replicates
      (n hours x 3 seeds) with the same pooling rule as the data (S1: sqrt(max(
      median CV^2, 0)); others: median). "One implementation for data and models".
  R2  Descriptive held-out comparison (reported only): the held-out day's hours are
      simulated with the fold's fit using the calibration namespace with fit id =
      the held-out day (seeds the fold's own fit never used), 3 per hour.
  R3  Rate-band holdouts (reported only): band b's hours on all six days are
      simulated with the without-band-b fit, using that fit id's calibration seeds;
      the S1 error is max over windows |sim - obs| against the frozen S1 tolerance.
  R4  An invalid fold fit is recorded as a failing fold with no safety violation and
      its queue test isn't run (A3.4); the frozen rule() then decides.
  R5  Boundary proximity: a coordinate of the best theta within 1% of its bound
      width of either bound (A3 addendum 2).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import multiprocessing as mp
import subprocess
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np

from relay.traffic import higher_order as ho
from relay.traffic.burstiness import BurstinessModel
from relay.traffic.generate import BIN_S, cox_arrivals
from relay.traffic.queueing import queue_metrics, servers_for
from relay.traffic.stats import moving_average_trend, per_second_counts

import common
import cycle2_config as cfg
import cycle2_data
import cycle2_optimizer as opt
import cycle2_seeds as seeds
import cycle2_targets as tg
import cycle2_validation as val

ROOT = Path(__file__).resolve().parents[1]
Theta = Sequence[float] | np.ndarray
OUT_DIR = Path("analysis/results/cycle2/candidate-d")
VARIANT = "D1"
SCENARIO = "trend"  # A3.8: sigma extrapolates by its power law; tau is constant
BOUNDARY_FRACTION = 0.01  # R5
S1_RESULT_SHA256 = "1a2fb0428fdb6224e94b1afff470a9f7f0d9bfd43c77f1aad365e57c79463f72"
# Pins of the D procedure modules (identical to tests/test_cycle2_d_domain.py).
PROCEDURE_SHA256 = {
    "analysis/cycle2_optimizer.py": "11fc05677988503a4e899285134da0206b35f8ab1f73fb2ccd301074bb2f3921",
    "analysis/cycle2_seeds.py": "058a72ca05c29ffbbcc2a25c4d91e3e75051b20f4a1170cf2aff6faf050ca042",
    "analysis/cycle2_targets.py": "f0837126afee47b977df64ee6da276f7c5803dee179d548edcece801b4d22e8a",
}  # fmt: skip
PROVENANCE_FILES = (
    "analysis/cycle2_candidate_d.py",
    "analysis/cycle2_config.py",
    "src/relay/traffic/burstiness.py",
    "src/relay/traffic/generate.py",
    "src/relay/traffic/higher_order.py",
    "src/relay/traffic/stats.py",
    "src/relay/traffic/queueing.py",
)


# ---- model --------------------------------------------------------------------------


def model_from_theta(theta: Theta) -> BurstinessModel:
    p = opt.from_theta([float(x) for x in theta])
    lo, hi = cfg.RATE_RANGE_RPS
    return BurstinessModel(name=VARIANT, a=p["a"], b=p["b"], band_rates=(1.0,),
                           band_taus=(p["tau_s"],), rate_min=lo, rate_max=hi)  # fmt: skip


POISSON = BurstinessModel("poisson", 0.0, 0.0, (1.0,), (1.0,), 0.0, 1e12)


def simulate(model: BurstinessModel, lam: np.ndarray, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return cox_arrivals(SimpleNamespace(burstiness=model), lam, rng, SCENARIO, 3600.0)  # type: ignore[arg-type]


# ---- data ---------------------------------------------------------------------------


def development_rows() -> list[dict[str, Any]]:
    """Eligible development hours: times, trend at 0.1 s, band and Azure S1-S4 components."""
    cycle2_data.enter_cycle2_mode()
    days = cycle2_data.load_development()
    if tuple(days) != cycle2_data.DEVELOPMENT_DAYS or cycle2_data.HOLDOUT_DATE in days:
        raise RuntimeError("development days differ from the frozen set")
    rows = []
    for day, arr in days.items():
        for h, th in common.hours(common.dejitter(arr["t"])):
            rate = len(th) / 3600
            band = common.band_of(rate)
            if rate < cfg.MIN_ELIGIBLE_RATE or band is None:
                continue
            trend = moving_average_trend(per_second_counts(th, 3600))
            lam = np.repeat(trend, int(round(1 / BIN_S)))
            lo, hi = cfg.RATE_RANGE_RPS
            rows.append({"day": day, "hour": h, "rate": rate, "band": band, "times": th,
                         "lam": lam, "stats": tg.hour_components(th),
                         "out_of_range_fraction": float(np.mean((lam < lo) | (lam > hi)))})  # fmt: skip
    return rows


# ---- preflight ----------------------------------------------------------------------


def _sha(path: str | Path) -> str:
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def preflight(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Fail closed unless every frozen artefact matches its recorded identity."""
    record = json.loads((ROOT / "analysis/cycle2_validation_freeze.json").read_text())
    pinned = {**record["implementation_sha256"], **record["audit"]["code_sha256"],
              **record["audit"]["results_sha256"], **PROCEDURE_SHA256,
              "analysis/results/cycle2/tolerances-s1.json": S1_RESULT_SHA256,
              cfg.DISPERSION_RESULT: cfg.DISPERSION_RESULT_SHA256}  # fmt: skip
    bad = {p: h for p, h in pinned.items() if _sha(p) != h}
    if bad:
        raise RuntimeError(f"frozen artefacts differ from their recorded identity: {sorted(bad)}")
    if (val.EQUIVALENCE_BOUND, val.SAFETY_BOUNDS, val.NEARZERO_CAP, val.FOLDS_REQUIRED) != (
        1.40, (0.5, 2.0), 0.10, 3
    ):  # fmt: skip
        raise RuntimeError("validator constants differ from Amendment 1")
    c1 = opt.to_theta(*(cfg.D_CYCLE1_START[k] for k in ("a", "b", "tau_s")))
    starts = opt.starts(np.array(cfg.D_THETA_LOWER), np.array(cfg.D_THETA_UPPER), c1)
    if [tuple(float(x) for x in s) for s in starts] != list(cfg.D_STARTS_THETA):
        raise RuntimeError("starts differ from the frozen D_STARTS_THETA")
    out: dict[str, Any] = {"pinned_sha256": pinned,
                           "caches": json.loads(cycle2_data.MANIFEST.read_text())["files"]}  # fmt: skip
    if rows is not None:
        frozen = tg.frozen_dispersion()
        if (
            tg.full_development_sd(rows, cycle2_data.DEVELOPMENT_DAYS)
            != frozen["full_development_sd"]
        ):
            raise RuntimeError("Azure components don't reproduce the frozen dispersion")
        if tg.rate_range(rows) != cfg.RATE_RANGE_RPS:
            raise RuntimeError("Azure rate range differs from the frozen range")
        out["azure_reproduces_frozen_dispersion"] = True
    return out


def provenance() -> dict[str, Any]:
    def git(*args: str) -> str:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                              check=True).stdout.strip()  # fmt: skip

    return {"git_head": git("rev-parse", "HEAD"), "git_dirty": git("status", "--porcelain"),
            "files_sha256": {p: _sha(p) for p in PROVENANCE_FILES},
            "wednesday_accessed": False, "raw_trace_accessed": False}  # fmt: skip


# ---- fits ---------------------------------------------------------------------------


def fit_specs() -> list[dict[str, Any]]:
    days = cycle2_data.DEVELOPMENT_DAYS
    specs: list[dict[str, Any]] = [
        {"fit": "all", "training_days": list(days), "without_band": None}
    ]
    specs += [{"fit": d, "training_days": [x for x in days if x != d], "without_band": None}
              for d in days]  # fmt: skip
    specs += [{"fit": f"without-band-{label}", "training_days": list(days), "without_band": b}
              for b, label in enumerate(tg.BAND_LABELS)]  # fmt: skip
    return specs


def fit_rows(rows: list[dict[str, Any]], spec: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        r for r in rows if r["day"] in spec["training_days"] and r["band"] != spec["without_band"]
    ]


def simulated_components(
    theta: Theta, rows: list[dict[str, Any]], fit_id: str, with_s5: bool = False
) -> list[dict[str, Any]]:
    """One record per (hour, replicate) with its S1-S4 components (and S5 if asked)."""
    model = model_from_theta(theta)
    out = []
    for r in rows:
        for rep in range(cfg.CALIBRATION_SEEDS_PER_HOUR):
            t = simulate(model, r["lam"], seeds.calibration_seed(fit_id, r["day"], r["hour"], rep))
            stats = tg.hour_components(t)
            if with_s5:
                stats.update(
                    {k: v for k, v in ho.hour_statistics(t).items() if ho.is_diagnostic_only(k)}
                )
            out.append({"day": r["day"], "hour": r["hour"], "band": r["band"], "stats": stats})
    return out


def pooled_by_band(
    records: list[dict[str, Any]], components: Sequence[str]
) -> dict[str, dict[str, float]]:
    """R1: band-pooled values over all hour-replicates of each band."""
    out = {}
    for b, label in enumerate(tg.BAND_LABELS):
        rs = [r for r in records if r["band"] == b]
        if rs:
            out[label] = {c: tg.pooled(rs, c) for c in components}
    return out


def make_objective(
    rows: list[dict[str, Any]], fold: dict[str, Any], fit_id: str
) -> Callable[[np.ndarray], float]:
    def objective(theta: np.ndarray) -> float:
        sim = pooled_by_band(simulated_components(theta, rows, fit_id), tg.TARGET_COMPONENTS)
        return tg.loss(sim, fold)[0]

    return objective


def boundary_proximity(theta: Theta) -> dict[str, Any]:
    """R5: per coordinate, distance to the nearest bound as a fraction of the bound width."""
    lo, hi = np.array(cfg.D_THETA_LOWER), np.array(cfg.D_THETA_UPPER)
    x = np.asarray(theta, float)
    frac = np.minimum(x - lo, hi - x) / (hi - lo)
    names = ("log_a", "b", "log_tau")
    return {"distance_fraction": dict(zip(names, frac.round(6).tolist(), strict=True)),
            "near_bound": [n for n, f in zip(names, frac, strict=True) if f < BOUNDARY_FRACTION]}  # fmt: skip


def run_fit(spec: dict[str, Any]) -> dict[str, Any]:
    rows = _ROWS
    frows = fit_rows(rows, spec)
    full_sd = tg.frozen_dispersion()["full_development_sd"]
    fold = tg.fold_targets_and_weights(frows, spec["training_days"], full_sd)
    objective = make_objective(frows, fold, spec["fit"])
    t0 = time.time()
    result = opt.fit(objective, np.array(cfg.D_THETA_LOWER), np.array(cfg.D_THETA_UPPER),
                     [np.array(s) for s in cfg.D_STARTS_THETA])  # fmt: skip
    elapsed = time.time() - t0
    out: dict[str, Any] = {**spec, "training_days": [common.DAYS[d] for d in spec["training_days"]],
                           "hours_in_loss": len(frows), "fold": fold, "elapsed_s": round(elapsed, 1),
                           "optimizer": result}  # fmt: skip
    if result["best_theta"] is not None:
        best = result["best_theta"]
        sims = simulated_components(best, frows, spec["fit"], with_s5=True)
        sim = pooled_by_band(sims, tg.TARGET_COMPONENTS)
        total, residuals = tg.loss(sim, fold)
        out["recomputed_best_objective"] = total
        out["deterministic"] = total == result["best_objective"]
        out["in_sample"] = {
            "simulated": pooled_by_band(sims, tg.REPORT_COMPONENTS),
            "observed": {label: {c: tg.pooled([r for r in frows if r["band"] == b], c)
                                 for c in tg.REPORT_COMPONENTS}
                         for b, label in enumerate(tg.BAND_LABELS)
                         if any(r["band"] == b for r in frows)},
            "residual_z": residuals,
            "s5_simulated": pooled_by_band(sims, _s5_keys(sims)),
        }  # fmt: skip
        out["boundary"] = boundary_proximity(best)
    print(f"fit {spec['fit']}: {result['termination']} after {result['evaluations']} evaluations, "
          f"L = {result['best_objective']}, {elapsed / 60:.1f} min", flush=True)  # fmt: skip
    return out


def _s5_keys(records: list[dict[str, Any]]) -> list[str]:
    return sorted(k for k in records[0]["stats"] if ho.is_diagnostic_only(k)) if records else []


_ROWS: list[dict[str, Any]] = []


def _fit_and_save(spec: dict[str, Any]) -> str:
    result = run_fit(spec)
    path = OUT_DIR / f"fit-{spec['fit']}.json"
    path.write_text(json.dumps(result, default=float) + "\n")
    return str(path)


def main_fit() -> None:
    global _ROWS
    _ROWS = development_rows()
    pre = preflight(_ROWS)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "fit-run.json").write_text(json.dumps({
        "started_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "preflight": pre, "provenance": provenance(),
        "out_of_range_fraction_by_hour": {f"{common.DAYS[r['day']]} {r['hour']:02d}":
                                          r["out_of_range_fraction"] for r in _ROWS},
    }, indent=1) + "\n")  # fmt: skip
    specs = sorted(fit_specs(), key=lambda s: -len(fit_rows(_ROWS, s)))  # longest first
    ctx = mp.get_context("fork")  # workers inherit the guard, the rows and the settings
    with ctx.Pool(2) as pool:
        for path in pool.imap_unordered(_fit_and_save, specs):
            print(f"wrote {path}", flush=True)


# ---- evaluation -----------------------------------------------------------------------


def queue_fold(theta: Theta, day: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Per eligible hour of `day`: model, Poisson and Azure p95/p99 per cell (A3.9)."""
    model = model_from_theta(theta)
    hours = []
    for r in sorted((r for r in rows if r["day"] == day), key=lambda r: r["hour"]):
        cells: dict[str, list[dict[str, float]]] = {"model": [], "poisson": [], "azure": []}
        for i, (s, rho) in enumerate(val.CELLS):
            c = servers_for(r["rate"], s, rho)
            runs: dict[str, list[dict[str, float]]] = {"model": [], "poisson": []}
            for rep in range(seeds.VALIDATION_REPLICATES):
                for name, m, stream in (("model", model, "D"), ("poisson", POISSON, "poisson")):
                    t = simulate(m, r["lam"], seeds.validation_seed(stream, day, r["hour"], i, rep))
                    q = queue_metrics(t, c, s, 3600.0)
                    runs[name].append({"p95": q.p95, "p99": q.p99})
            for name, rs in runs.items():
                cells[name].append({k: float(np.median([x[k] for x in rs])) for k in val.METRICS})
            q = queue_metrics(r["times"], c, s, 3600.0)
            cells["azure"].append({"p95": q.p95, "p99": q.p99})
        hours.append({"hour": r["hour"], "rate": r["rate"], "band": r["band"],
                      "out_of_range_fraction": r["out_of_range_fraction"], **cells})  # fmt: skip
    return {"day": day, "weekday": common.DAYS[day], "hours": hours}


def descriptive_heldout(theta: Theta, day: str, rows: list[dict[str, Any]],
                        fold: dict[str, Any]) -> dict[str, Any]:  # fmt: skip
    """R2: S1-S4 (and S5) of the held-out day, simulated vs Azure, by band. Reported only."""
    drows = [r for r in rows if r["day"] == day]
    sims = simulated_components(theta, drows, day, with_s5=True)
    tol = tg.frozen_dispersion()["reporting_tolerances_s2_s4"]
    out = {}
    for b, label in enumerate(tg.BAND_LABELS):
        hs = [r for r in drows if r["band"] == b]
        if not hs:
            continue
        sim_rs = [s for s in sims if s["band"] == b]
        s5_keys = _s5_keys(sim_rs)
        az_s5 = [ho.hour_statistics(r["times"]) for r in hs]
        sim = {c: tg.pooled(sim_rs, c) for c in tg.REPORT_COMPONENTS}
        obs = {c: tg.pooled(hs, c) for c in tg.REPORT_COMPONENTS}
        err = {c: sim[c] - obs[c] for c in tg.REPORT_COMPONENTS}
        s1_max = max(abs(err[c]) for c in tg.S1)
        out[label] = {
            "hours": len(hs), "simulated": sim, "observed": obs, "error": err,
            "z_vs_fold_sd": ({c: err[c] / fold["sd"][label][c] for c in tg.TARGET_COMPONENTS}
                             if label in fold["sd"] else None),
            "s1_max_abs_error": s1_max, "s1_tolerance": cfg.S1_TOLERANCES[label],
            "s1_within_tolerance": s1_max <= cfg.S1_TOLERANCES[label],
            "s2_s4_within_tolerance": {c: abs(err[c]) <= tol[label][c] for c in tol[label]},
            "s5_simulated": {k: tg.pooled(sim_rs, k) for k in s5_keys},
            "s5_azure": {k: float(np.median([x[k] for x in az_s5])) for k in s5_keys},
        }  # fmt: skip
    return out


def band_holdout(theta: Theta, band: int, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """R3: S1 of band b simulated with the without-band-b fit vs Azure (all six days)."""
    label = tg.BAND_LABELS[band]
    hs = [r for r in rows if r["band"] == band]
    sims = simulated_components(theta, hs, f"without-band-{label}")
    sim = {c: tg.pooled(sims, c) for c in tg.S1}
    obs = {c: tg.pooled(hs, c) for c in tg.S1}
    err = {c: sim[c] - obs[c] for c in tg.S1}
    m = max(abs(v) for v in err.values())
    return {"hours": len(hs), "simulated": sim, "observed": obs, "error": err, "max_abs_error": m,
            "tolerance": cfg.S1_TOLERANCES[label], "within_tolerance": m <= cfg.S1_TOLERANCES[label]}  # fmt: skip


def _load_fit(fit_id: str) -> dict[str, Any]:
    result: dict[str, Any] = json.loads((OUT_DIR / f"fit-{fit_id}.json").read_text())
    return result


def _evaluate_day(day: str) -> dict[str, Any]:
    fit = _load_fit(day)
    if not fit["optimizer"]["valid"]:
        return {"day": day, "fit_valid": False}
    theta = fit["optimizer"]["best_theta"]
    out = {"day": day, "fit_valid": True, "theta": theta,
           "queue": queue_fold(theta, day, _ROWS),
           "descriptive": descriptive_heldout(theta, day, _ROWS, fit["fold"])}  # fmt: skip
    print(f"evaluated {common.DAYS[day]}", flush=True)
    return out


def _fold_result(q: dict[str, Any]) -> dict[str, Any]:
    m, p, a = (val._as_array([h[k] for h in q["hours"]]) for k in ("model", "poisson", "azure"))
    return val.fold_result(m, p, a)


def main_evaluate() -> None:
    global _ROWS
    _ROWS = development_rows()
    pre = preflight(_ROWS)
    full = _load_fit("all")
    if not full["optimizer"]["valid"]:
        verdict: dict[str, Any] = {"label": "INVALID PROCEDURE",
                                   "reason": "full-development fit invalid (A3.4)"}  # fmt: skip
        (OUT_DIR / "evaluation.json").write_text(json.dumps({"verdict": verdict}, indent=1) + "\n")
        print(verdict)
        return
    ctx = mp.get_context("fork")
    with ctx.Pool(2) as pool:
        per_day = dict(zip(cycle2_data.DEVELOPMENT_DAYS,
                           pool.map(_evaluate_day, cycle2_data.DEVELOPMENT_DAYS), strict=True))  # fmt: skip
    gating = {d: per_day[d] for d in val.GATING_FOLDS}
    if all(f["fit_valid"] for f in gating.values()):
        validation = val.validate({d: {k: [h[k] for h in f["queue"]["hours"]]
                                       for k in ("model", "poisson", "azure")}
                                   for d, f in gating.items()})  # fmt: skip
    else:  # R4
        cycle2_data.enter_cycle2_mode()
        folds = {d: (_fold_result(f["queue"]) if f["fit_valid"] else
                     {"passed": False, "safety_violation": False, "fit_invalid": True})
                 for d, f in gating.items()}  # fmt: skip
        validation = {"folds": folds, **val.rule(folds)}
    reported = {d: _fold_result(per_day[d]["queue"])
                for d in cfg.REPORTED_FOLDS if per_day[d]["fit_valid"]}  # fmt: skip
    holdouts = {}
    for b, label in enumerate(tg.BAND_LABELS):
        f = _load_fit(f"without-band-{label}")
        holdouts[label] = (band_holdout(f["optimizer"]["best_theta"], b, _ROWS)
                           if f["optimizer"]["valid"] else {"fit_valid": False})  # fmt: skip
    verdict = {"label": "PASS" if validation["passed"] else "FAIL",
               "folds_passing": validation["folds_passing"],
               "folds_with_safety_violation": validation["folds_with_safety_violation"],
               "resolution_statement": val.RESOLUTION_STATEMENT}  # fmt: skip
    record = {
        "evaluated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "preflight": pre, "provenance": provenance(),
        "verdict": verdict, "validation_gating": validation, "validation_reported": reported,
        "per_day": per_day, "band_holdouts": holdouts,
    }  # fmt: skip
    (OUT_DIR / "evaluation.json").write_text(json.dumps(record, default=float) + "\n")
    print(json.dumps(verdict, indent=1))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("fit", "evaluate"))
    args = parser.parse_args()
    if args.phase == "fit":
        main_fit()
    else:
        main_evaluate()


if __name__ == "__main__":
    main()
