"""Candidate-independent criterion audit (Cycle 2 preregistration, section 7).

Usage: uv run python analysis/criterion_audit.py              # original audit (R = 50)
       uv run python analysis/criterion_audit.py --expanded   # 200-replicate audit

Asks whether the provisional internal pass rule (3 of 4 gating folds pass all three
frozen queue criteria, and no catastrophic cell) is statistically coherent, before
any Cycle 2 candidate exists:

N1  self-consistency: the "model" IS the truth process (Cycle 1 C1, fixed; or the
    within-band bootstrap). One further realisation plays Azure; repeated R times.
N2  Azure-vs-Azure: real Azure hours against the bootstrap built from the OTHER
    development days.

Cache-only: reads development days through cycle2_data after enter_cycle2_mode().
Writes analysis/results/cycle2/criterion-audit.json.
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
import multiprocessing as mp
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np

from relay.traffic.burstiness import BurstinessModel, load_candidate
from relay.traffic.generate import cox_arrivals
from relay.traffic.queueing import CellVerdict, accept, as_dict, judge, judge_cell, queue_metrics
from relay.traffic.stats import moving_average_trend, per_second_counts

import common
import cycle2_config as cfg
import cycle2_data

OUT = Path("analysis/results/cycle2/criterion-audit.json")
OUT_EXPANDED = Path("analysis/results/cycle2/criterion-audit-200.json.gz")
# Set in main() before workers fork, so every worker sees the same values.
_REPLICATES = cfg.AUDIT_REFERENCE_REPLICATES
_ENTROPY = cfg.AUDIT_SEED_ENTROPY
REFERENCE = Path("traffic/reference/azure_code_burstiness.json")
CELLS = [(s, rho) for s in cfg.SERVICE_TIMES_S for rho in cfg.UTILISATIONS]
PROCESS_CODES = {"poisson": 1, "cycle1_C1": 2, "bootstrap": 3}
ROLE_CODES = {"model": 1, "reference": 2}


# ---- the bootstrap null instrument (comparator C) --------------------------------------


def bootstrap_counts(
    target_trend: np.ndarray,
    pool: list[tuple[np.ndarray, np.ndarray]],
    rng: np.random.Generator,
    mean_block_s: int = cfg.BOOTSTRAP_MEAN_BLOCK_S,
) -> tuple[np.ndarray, float]:
    """Per-second counts on `target_trend` from stationary-bootstrap source seconds.

    pool: (per-second counts, trend) of source hours. Returns counts and the fraction
    of seconds needing superposition (p > 1).
    """
    n = len(target_trend)
    src_idx = np.empty(n, dtype=int)
    src_sec = np.empty(n, dtype=int)
    t = 0
    while t < n:
        length = int(rng.geometric(1.0 / mean_block_s))
        k = int(rng.integers(len(pool)))
        u = int(rng.integers(n))
        end = min(n, t + length)
        src_idx[t:end] = k
        src_sec[t:end] = (u + np.arange(end - t)) % n
        t = end
    n_src = np.array([pool[k][0][u] for k, u in zip(src_idx, src_sec, strict=True)])
    e_src = np.array([pool[k][1][u] for k, u in zip(src_idx, src_sec, strict=True)])
    p = target_trend / e_src
    thin = rng.binomial(n_src.astype(int), np.clip(p, 0.0, 1.0))
    extra = rng.poisson(np.clip(p - 1.0, 0.0, None) * n_src)
    counts = np.where(p <= 1.0, thin, n_src + extra)
    return counts.astype(int), float(np.mean(p > 1.0))


def within_second(counts: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    b = np.repeat(np.arange(len(counts)), counts)
    return np.sort(b + rng.random(len(b)))


# ---- decision logic (section 6) ---------------------------------------------------------


def catastrophic_cell(model: dict[str, float], ref: dict[str, float], s: float) -> bool:
    """A p95/p99 ratio outside CATASTROPHIC_BOUNDS, or a one-sided near-zero failure at A = 0."""
    lo, hi = cfg.CATASTROPHIC_BOUNDS
    for key in ("p95", "p99"):
        mv = judge(model[key], ref[key], s)
        if mv.agrees_near_zero:
            continue
        if mv.fails_near_zero and ref[key] == 0:
            return True
        if mv.ratio is not None and not (lo <= mv.ratio <= hi):
            return True
    return False


def fold_verdict(
    model: list[dict[str, float]], poisson: list[dict[str, float]], ref: list[dict[str, float]]
) -> dict[str, Any]:
    """One fold: the three frozen criteria (clarified criterion 3) and the catastrophic check."""
    verdicts: list[CellVerdict] = []
    catastrophic = 0
    for m, p, r, (s, _rho) in zip(
        model, poisson, ref, CELLS * (len(model) // len(CELLS)), strict=True
    ):
        verdicts.append(judge_cell(m, p, r, s, cfg.CRITERION_3))
        catastrophic += catastrophic_cell(m, r, s)
    a = as_dict(accept(verdicts))
    return {**a, "catastrophic_cells": catastrophic}


def rule_passes(folds: list[dict[str, Any]]) -> bool:
    """>= FOLDS_REQUIRED folds pass all three criteria, and no fold has a catastrophic cell."""
    passing = sum(bool(f["passed"]) for f in folds)
    return passing >= cfg.FOLDS_REQUIRED and all(f["catastrophic_cells"] == 0 for f in folds)


# ---- per-fold computation ---------------------------------------------------------------


def _rng(process: str, fold: int, hour: int, role: str, rep: int) -> np.random.Generator:
    key = (PROCESS_CODES[process], fold, hour, ROLE_CODES.get(role, 0), rep)
    return np.random.default_rng(np.random.SeedSequence(_ENTROPY, spawn_key=key))


def _metrics(times: np.ndarray, rate: float) -> list[dict[str, float]]:
    out = []
    for s, rho in CELLS:
        q = queue_metrics(times, max(1, math.ceil(rate * s / rho)), s, 3600.0)
        out.append({"p95": q.p95, "p99": q.p99})
    return out


def _median(runs: list[list[dict[str, float]]]) -> list[dict[str, float]]:
    return [
        {k: float(np.median([r[i][k] for r in runs])) for k in ("p95", "p99")}
        for i in range(len(runs[0]))
    ]


_HOURS: dict[str, list[dict[str, Any]]] = {}
_C1: BurstinessModel | None = None


def _setup() -> None:
    global _C1
    cycle2_data.enter_cycle2_mode()
    days = cycle2_data.load_development()
    for day, arr in days.items():
        rows = []
        for h, th in common.hours(common.dejitter(arr["t"])):
            rate = len(th) / 3600
            band = common.band_of(rate)
            if rate < cfg.MIN_ELIGIBLE_RATE or band is None:
                continue
            per_s = per_second_counts(th, 3600)
            rows.append({"hour": h, "rate": rate, "band": band, "times": th,
                         "counts": per_s.astype(int), "trend": moving_average_trend(per_s)})  # fmt: skip
        _HOURS[day] = rows
    _C1 = load_candidate(json.loads(REFERENCE.read_text()), "C1")


def _pool(day: str, band: int, rate: float) -> list[tuple[np.ndarray, np.ndarray]]:
    src = [r for d, rows in _HOURS.items() if d != day for r in rows if r["band"] == band]
    higher = [r for r in src if r["rate"] >= rate]
    return [(r["counts"], r["trend"]) for r in (higher or src)]


def run_fold(fold_index: int) -> dict[str, Any]:
    day = cfg.GATING_FOLDS[fold_index]
    zero = BurstinessModel("poisson", 0.0, 0.0, (1.0,), (1.0,), 0.0, 1e12)
    hours = []
    for row in _HOURS[day]:
        h, rate, trend = row["hour"], row["rate"], row["trend"]
        lam = np.repeat(trend, 10)
        pool = _pool(day, row["band"], rate)

        superposed: list[float] = []

        def c1(rng: np.random.Generator, lam: np.ndarray = lam) -> np.ndarray:
            return cox_arrivals(SimpleNamespace(burstiness=_C1), lam, rng, "edge", 3600.0)  # type: ignore[arg-type]

        def boot(
            rng: np.random.Generator,
            trend: np.ndarray = trend,
            pool: list[tuple[np.ndarray, np.ndarray]] = pool,
            superposed: list[float] = superposed,
        ) -> np.ndarray:
            counts, frac = bootstrap_counts(trend, pool, rng)
            superposed.append(frac)
            return within_second(counts, rng)

        poisson = _median([
            _metrics(cox_arrivals(SimpleNamespace(burstiness=zero), lam,
                                  _rng("poisson", fold_index, h, "model", i), "edge", 3600.0), rate)  # type: ignore[arg-type]
            for i in range(cfg.SEEDS_PER_CELL)
        ])  # fmt: skip
        record: dict[str, Any] = {"hour": h, "rate": rate, "band": row["band"], "pool_hours": len(pool),
                                  "azure": _metrics(row["times"], rate), "poisson": poisson}  # fmt: skip
        for name, gen in (("cycle1_C1", c1), ("bootstrap", boot)):
            model = _median([_metrics(gen(_rng(name, fold_index, h, "model", i)), rate)
                             for i in range(cfg.SEEDS_PER_CELL)])  # fmt: skip
            refs = [_metrics(gen(_rng(name, fold_index, h, "reference", r)), rate)
                    for r in range(_REPLICATES)]  # fmt: skip
            record[name] = {"model": model, "references": refs}
        record["bootstrap_superposed_fraction"] = float(np.mean(superposed))
        hours.append(record)
        print(f"  {common.DAYS[day]} {h:02d} ({rate:.1f} rps) done", flush=True)
    return {"day": day, "weekday": common.DAYS[day], "hours": hours}


# ---- summary ---------------------------------------------------------------------------


def _flatten(hours: list[dict[str, Any]], getter: Any) -> list[dict[str, float]]:
    return [cell for h in hours for cell in getter(h)]


def summarise(folds: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    reps_n = len(folds[0]["hours"][0]["cycle1_C1"]["references"])
    for name in cfg.AUDIT_TRUTH_PROCESSES:
        per_fold: list[list[dict[str, Any]]] = []
        for f in folds:
            hours = f["hours"]
            model = _flatten(hours, lambda h, n=name: h[n]["model"])
            poisson = _flatten(hours, lambda h: h["poisson"])
            reps = [fold_verdict(model, poisson, _flatten(hours, lambda h, n=name, r=r: h[n]["references"][r]))
                    for r in range(reps_n)]  # fmt: skip
            per_fold.append(reps)
        rule = [rule_passes([per_fold[k][r] for k in range(len(folds))])
                for r in range(reps_n)]  # fmt: skip
        out[f"N1_{name}"] = {
            "P_rule": float(np.mean(rule)),
            "folds": {
                f["weekday"]: {
                    "pass_all_three": float(np.mean([v["passed"] for v in reps])),
                    "criterion_1": float(np.mean([v["criterion_1"] for v in reps])),
                    "criterion_2": float(np.mean([v["criterion_2"] for v in reps])),
                    "criterion_3": float(np.mean([v["criterion_3"] for v in reps])),
                    "catastrophic_false_alarm": float(np.mean([v["catastrophic_cells"] > 0 for v in reps])),
                    "in_band_cells_median": float(np.median([v["in_band"] for v in reps])),
                    "out_of_bounds_cells_median": float(np.median([v["out_of_bounds"] for v in reps])),
                    "beats_poisson_fraction_median": float(np.median([v["beats_poisson"] / max(1, v["non_tie"]) for v in reps])),
                }
                for f, reps in zip(folds, per_fold, strict=True)
            },
        }  # fmt: skip
    n2 = []
    for f in folds:
        hours = f["hours"]
        n2.append(fold_verdict(_flatten(hours, lambda h: h["bootstrap"]["model"]),
                               _flatten(hours, lambda h: h["poisson"]),
                               _flatten(hours, lambda h: h["azure"])))  # fmt: skip
    out["N2_azure_vs_azure"] = {"rule_passes": rule_passes(n2),
                                "folds": {f["weekday"]: v for f, v in zip(folds, n2, strict=True)}}  # fmt: skip
    n1_ok = all(
        out[f"N1_{n}"]["P_rule"] >= cfg.AUDIT_RULE_PASS_MIN for n in cfg.AUDIT_TRUTH_PROCESSES
    )
    fa_ok = all(v["catastrophic_false_alarm"] <= cfg.AUDIT_CATASTROPHIC_FALSE_ALARM_MAX
                for n in cfg.AUDIT_TRUTH_PROCESSES for v in out[f"N1_{n}"]["folds"].values())  # fmt: skip
    if not (n1_ok and fa_ok):
        decision = "STOP: rule poorly calibrated under the self-consistency null (N1)"
    elif not out["N2_azure_vs_azure"]["rule_passes"]:
        decision = "STOP: N1 coherent, but Azure-vs-Azure (N2) fails the rule"
    else:
        decision = "PROCEED: rule coherent (N1) and attainable (N2)"
    out["decision"] = {
        "n1_rule_ok": n1_ok,
        "catastrophic_false_alarm_ok": fa_ok,
        "verdict": decision,
    }
    return out


def main() -> None:
    global _REPLICATES, _ENTROPY
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expanded", action="store_true",
                        help="the predeclared 200-replicate audit (cycle2_config.AUDIT_EXPANDED)")  # fmt: skip
    args = parser.parse_args()
    out = OUT
    if args.expanded:
        _REPLICATES = int(cfg.AUDIT_EXPANDED["replicates"])
        _ENTROPY = int(cfg.AUDIT_EXPANDED["seed_entropy"])
        out = OUT_EXPANDED
    _setup()
    ctx = mp.get_context("fork")  # workers inherit the Cycle 2 guard, caches and settings
    with ctx.Pool(min(2, len(cfg.GATING_FOLDS))) as pool:
        folds = pool.map(run_fold, range(len(cfg.GATING_FOLDS)))
    summary = summarise(folds)
    out.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "preregistration": "docs/validation/phase-2-cycle-2-preregistration.md section 7"
        + (" and criterion-audit doc section 5 (expanded audit)" if args.expanded else ""),
        "replicates": _REPLICATES,
        "seed_entropy": _ENTROPY,
        "caches": json.loads(cycle2_data.MANIFEST.read_text())["files"],
        "wednesday_accessed": False,
        "summary": summary,
        "folds": folds,
    }
    text = json.dumps(record, default=float) + "\n"
    if out.suffix == ".gz":
        out.write_bytes(gzip.compress(text.encode(), mtime=0))
    else:
        out.write_text(text)
    print(json.dumps(summary, indent=1, default=float))


if __name__ == "__main__":
    main()
