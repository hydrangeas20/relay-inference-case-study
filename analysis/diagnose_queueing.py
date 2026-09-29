"""Diagnosis of the Thursday queueing failure (preregistration Amendment 2, A2.4).

Usage: uv run python analysis/diagnose_queueing.py

Question: why do C1/C2 reproduce Azure's 1-60 s rate-fluctuation curves while
overestimating queue tails? Uses TRAINING days and THURSDAY only (never Wednesday).
Nothing here tunes C1 or C2, defines a new candidate, changes a threshold or
searches parameters. The model runs use the same trend and seed scheme as the
Thursday validation (validate.py). Surrogate experiments transform arrival
streams to isolate one property at a time; they are diagnostics, not models.

Writes analysis/results/diagnosis-queueing/diagnosis.json. Figures:
uv run --with matplotlib python analysis/plot_diagnosis.py
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np

from relay.traffic.burstiness import BurstinessModel, load_candidate
from relay.traffic.generate import cox_arrivals
from relay.traffic.queueing import queue_metrics, servers_for
from relay.traffic.stats import (
    fit_sigma_tau,
    moving_average_trend,
    per_second_counts,
    rate_cv2,
)

import common
import validation_config as cfg

OUT = Path("analysis/results/diagnosis-queueing/diagnosis.json")
REFERENCE = Path("traffic/reference/azure_code_burstiness.json")
CELLS = ((0.2, 0.6), (0.2, 0.8), (1.0, 0.6), (1.0, 0.8))
FANO_WINDOWS = (0.1, 0.25, 1, 5, 10, 30, 60)
ACF_LAGS = (1, 2, 5, 10, 20, 30, 60, 120, 300)
PERSIST_LAGS = (1, 2, 5, 10, 20, 30)
BLOCKS = (1, 5, 15, 30, 60)
SEEDS_STATS = (1, 2, 3, 4, 5)
SEEDS_BLOCK = (1, 2, 3)
SEEDS_BIAS = tuple(range(1, 11))
SURROGATE_SEED = 20260929

_REF = json.loads(REFERENCE.read_text())
MODELS: dict[str, BurstinessModel] = {
    "C1": load_candidate(_REF, "C1"),
    "C2": load_candidate(_REF, "C2"),
    "Poisson": BurstinessModel("poisson", 0.0, 0.0, (1.0,), (1.0,), 0.0, 1e12),
}


def generate(name: str, trend: np.ndarray, hour: int, seed: int) -> np.ndarray:
    """The validation's arrivals for this hour and seed (validate.py's seed scheme)."""
    offset = cfg.POISSON_SEED_OFFSET if name == "Poisson" else 0
    rng = np.random.default_rng(offset + cfg.MODEL_SEED_BASE * hour + seed)
    model = SimpleNamespace(burstiness=MODELS[name])
    return cox_arrivals(model, np.repeat(trend, 10), rng, "edge", 3600.0)  # type: ignore[arg-type]


def eligible_hours(split: str) -> list[tuple[str, int, float, np.ndarray]]:
    rows = []
    for day, arr in common.load_split(split).items():
        t = common.dejitter(arr["t"])
        for h, th in common.hours(t):
            rate = len(th) / 3600
            if rate >= common.MIN_ELIGIBLE_RATE and common.band_of(rate) is not None:
                rows.append((common.DAYS[day], h, rate, th))
    return rows


# ---- arrival-process statistics ------------------------------------------------------


def _runs(mask: np.ndarray, values: np.ndarray | None = None) -> tuple[list[int], list[float]]:
    runs, areas, n, area = [], [], 0, 0.0
    for i, m in enumerate(mask):
        if m:
            n += 1
            area += 0.0 if values is None else float(values[i])
        elif n:
            runs.append(n)
            areas.append(area)
            n, area = 0, 0.0
    if n:
        runs.append(n)
        areas.append(area)
    return runs, areas


def arrival_stats(t: np.ndarray, trend: np.ndarray) -> dict[str, float]:
    out: dict[str, float] = {}
    gaps = np.diff(t)
    out["gap_cv"] = float(gaps.std() / gaps.mean())
    for q in (1, 50, 99, 99.9):
        out[f"gap_q{q}_x_mean"] = float(np.percentile(gaps, q) / gaps.mean())
    for w in FANO_WINDOWS:
        n = np.histogram(t, bins=np.arange(0, 3600 + 1e-9, w))[0]
        tr = np.repeat(trend, round(1 / w)) * w if w < 1 else trend.reshape(-1, int(w)).sum(1)
        out[f"fano_{w}"] = float(np.var(n - tr) / np.mean(n))  # around the trend
        if w <= 1:
            k = n / np.mean(n)
            out[f"count_{w}_q999_x_mean"] = float(np.percentile(k, 99.9))
    n1 = per_second_counts(t, 3600)
    z = n1 / trend - 1
    zc = z - z.mean()
    for lag in ACF_LAGS:
        out[f"acf_{lag}"] = float(np.mean(zc[:-lag] * zc[lag:]) / np.mean(zc * zc))
    r10 = n1.reshape(-1, 10).sum(1) / trend.reshape(-1, 10).sum(1) - 1
    sd = r10.std()
    out["r10_sd"] = float(sd)
    out["r10_skew"] = float(np.mean((r10 - r10.mean()) ** 3) / sd**3)
    out["r10_excess_kurtosis"] = float(np.mean((r10 - r10.mean()) ** 4) / sd**4 - 3)
    for q in (1, 99, 99.9):
        out[f"r10_q{q}"] = float(np.percentile(r10, q))
    sm = np.convolve(z, np.ones(10) / 10, mode="same")
    for k in (1, 2):
        runs, _ = _runs(sm > k * sm.std())
        out[f"run_above_{k}sd_mean_s"] = float(np.mean(runs)) if runs else 0.0
        out[f"run_above_{k}sd_max_s"] = float(max(runs)) if runs else 0.0
    for thr in (0.1, 0.25, 0.4):
        r5 = np.convolve(z, np.ones(5) / 5, mode="same")
        runs, areas = _runs(r5 > thr, r5 - thr)
        out[f"exceed_{thr}_frac"] = float(np.mean(r5 > thr))
        out[f"exceed_{thr}_runs_per_hour"] = float(len(runs))
        out[f"exceed_{thr}_run_mean_s"] = float(np.mean(runs)) if runs else 0.0
        out[f"exceed_{thr}_area_mean"] = float(np.mean(areas)) if areas else 0.0
    r3 = np.convolve(z, np.ones(3) / 3, mode="same")
    hi, lo = r3 > np.quantile(r3, 0.95), r3 < np.quantile(r3, 0.05)
    for lag in PERSIST_LAGS:
        out[f"persist_top5_{lag}"] = float(np.mean(hi[lag:][hi[:-lag]]))
        out[f"persist_bottom5_{lag}"] = float(np.mean(lo[lag:][lo[:-lag]]))
    return out


def _mean_stats(ds: list[dict[str, float]]) -> dict[str, float]:
    return {k: float(np.mean([d[k] for d in ds])) for k in ds[0]}


# ---- queue helpers and surrogates ----------------------------------------------------


def p95_p99(t: np.ndarray, rate: float) -> dict[str, list[float]]:
    out = {}
    for s, rho in CELLS:
        m = queue_metrics(t, servers_for(rate, s, rho), s, 3600.0)
        out[f"{s}_{rho}"] = [m.p95, m.p99]
    return out


def within_second(counts: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Keep per-second counts; place arrivals uniformly inside each second."""
    b = np.repeat(np.arange(len(counts)), counts.astype(int))
    return np.sort(b + rng.random(len(b)))


def swap_marginal(order: np.ndarray, values: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Counts with `order`'s temporal ranks and `values`'s distribution (ties random)."""
    ranks = np.lexsort((rng.random(len(order)), order))
    out = np.empty_like(values)
    out[ranks] = np.sort(values)
    return out


def block_shuffle(n: np.ndarray, block: int, rng: np.random.Generator) -> np.ndarray:
    """Shuffle B-second blocks within each 10-minute window (keeps the trend)."""
    out = n.copy()
    for w0 in range(0, len(n), 600):
        seg = n[w0 : w0 + 600]
        k = len(seg) // block
        blocks = seg[: k * block].reshape(k, block)
        out[w0 : w0 + k * block] = blocks[rng.permutation(k)].ravel()
    return out


def _median_cells(runs: list[dict[str, list[float]]]) -> dict[str, list[float]]:
    return {c: np.median([r[c] for r in runs], axis=0).tolist() for c in runs[0]}


# ---- analyses ------------------------------------------------------------------------


def thursday(rows: list[tuple[str, int, float, np.ndarray]]) -> list[dict[str, Any]]:
    rng = np.random.default_rng(SURROGATE_SEED)
    c1 = MODELS["C1"]
    out = []
    for _, h, rate, th in rows:
        n_az = per_second_counts(th, 3600).astype(int)
        trend = moving_average_trend(n_az.astype(float))
        row: dict[str, Any] = {"hour": h, "rate": rate, "stats": {}, "surrogates": {}}
        row["stats"]["Azure"] = arrival_stats(th, trend)
        row["surrogates"]["Azure"] = {
            "original": p95_p99(th, rate),
            "within_second": p95_p99(within_second(n_az, rng), rate),
        }
        blocks: dict[str, dict[str, float]] = {"Azure": {}}
        for s, rho in ((1.0, 0.8), (0.2, 0.8)):
            c = servers_for(rate, s, rho)
            for b in BLOCKS:
                t_b = within_second(block_shuffle(n_az, b, rng), rng)
                blocks["Azure"][f"{s}_{rho}_B{b}"] = queue_metrics(t_b, c, s, 3600.0).p99
        for name in ("C1", "C2", "Poisson"):
            ts = [generate(name, trend, h, sd) for sd in SEEDS_STATS]
            row["stats"][name] = _mean_stats([arrival_stats(t, trend) for t in ts])
            ns = [per_second_counts(t, 3600).astype(int) for t in ts]
            row["surrogates"][name] = {
                "original": _median_cells([p95_p99(t, rate) for t in ts]),
                "within_second": _median_cells([p95_p99(within_second(n, rng), rate) for n in ns]),
                "model_order_azure_marginal": _median_cells(
                    [p95_p99(within_second(swap_marginal(n, n_az, rng), rng), rate) for n in ns]
                ),
                "azure_order_model_marginal": _median_cells(
                    [p95_p99(within_second(swap_marginal(n_az, n, rng), rng), rate) for n in ns]
                ),
            }
            if name != "Poisson":
                blocks[name] = {}
                for s, rho in ((1.0, 0.8), (0.2, 0.8)):
                    c = servers_for(rate, s, rho)
                    blocks[name][f"{s}_{rho}_B0"] = float(
                        np.median([queue_metrics(ts[i - 1], c, s, 3600.0).p99 for i in SEEDS_BLOCK])
                    )
                    for b in BLOCKS:
                        v = [
                            queue_metrics(
                                within_second(block_shuffle(ns[i - 1], b, rng), rng), c, s, 3600.0
                            ).p99
                            for i in SEEDS_BLOCK
                        ]
                        blocks[name][f"{s}_{rho}_B{b}"] = float(np.median(v))
        blocks["Azure"].update(
            {f"{s}_{rho}_B0": queue_metrics(th, servers_for(rate, s, rho), s, 3600.0).p99
             for s, rho in ((1.0, 0.8), (0.2, 0.8))}
        )  # fmt: skip
        row["block_shuffle_p99"] = blocks
        # Estimator reading on C1 traffic at this hour's trend, and each hour's own sigma.
        sa, ta, _ = fit_sigma_tau(np.clip(rate_cv2(th, 3600), 1e-12, None))
        fits = [
            fit_sigma_tau(np.clip(rate_cv2(generate("C1", trend, h, sd), 3600), 1e-12, None))
            for sd in SEEDS_BIAS
        ]
        true_sigma = float(c1.sigma(np.array([rate]), "edge")[0])
        row["sigma"] = {
            "azure_hour_estimate": float(sa),
            "azure_hour_tau_estimate": float(ta),
            "c1_true": true_sigma,
            "c1_estimated_on_generated": float(np.mean([f[0] for f in fits])),
        }
        out.append(row)
        print(f"Thu {h:02d} ({rate:.1f} rps)", flush=True)
    return out


def training(rows: list[tuple[str, int, float, np.ndarray]]) -> list[dict[str, Any]]:
    out = []
    for day, h, rate, th in rows:
        trend = moving_average_trend(per_second_counts(th, 3600))
        row: dict[str, Any] = {"day": day, "hour": h, "rate": rate, "stats": {}, "p99": {}}
        row["stats"]["Azure"] = arrival_stats(th, trend)
        gens = {nm: [generate(nm, trend, h, sd) for sd in SEEDS_STATS] for nm in ("C1", "Poisson")}
        for nm, ts in gens.items():
            row["stats"][nm] = _mean_stats([arrival_stats(t, trend) for t in ts])
        for s, rho in ((0.2, 0.8), (1.0, 0.8)):
            c = servers_for(rate, s, rho)
            row["p99"][f"{s}_{rho}"] = {
                "Azure": queue_metrics(th, c, s, 3600.0).p99,
                **{
                    nm: float(np.median([queue_metrics(t, c, s, 3600.0).p99 for t in ts]))
                    for nm, ts in gens.items()
                },
            }
        out.append(row)
    print(f"training: {len(out)} hours", flush=True)
    return out


def _rank(a: np.ndarray) -> np.ndarray:
    return np.argsort(np.argsort(a)).astype(float)


def spearman(x: list[float], y: list[float], n_perm: int = 5000) -> dict[str, float]:
    a, b = np.asarray(x, float), np.asarray(y, float)
    keep = ~(np.isnan(a) | np.isnan(b))
    ra, rb = _rank(a[keep]), _rank(b[keep])
    r = float(np.corrcoef(ra, rb)[0, 1])
    rng = np.random.default_rng(0)
    null = [abs(np.corrcoef(ra, rng.permutation(rb))[0, 1]) for _ in range(n_perm)]
    return {"rho": round(r, 3), "n": int(keep.sum()), "perm_p": float(np.mean(np.array(null) >= abs(r)))}


def associations(thu: list[dict[str, Any]]) -> dict[str, Any]:
    """Across Thursday hours: arrival discrepancy vs log(model p99 / Azure p99).

    Queue errors are the stored validation cells (20 seeds). Exploratory: about ten
    features x eight cells, so an uncorrected p < 0.05 is expected by chance.
    """
    validation = json.loads(Path("analysis/results/validation-validation.json").read_text())
    by_hour = {r["hour"]: r for r in thu}
    features: dict[str, Callable[[dict[str, Any], str], float]] = {
        "log rate": lambda r, c: float(np.log(r["rate"])),
        "log(model sigma / hour's Azure sigma)": lambda r, c: float(
            np.log(r["sigma"]["c1_true"] / r["sigma"]["azure_hour_estimate"])
        ),
        "diff skew (10 s)": lambda r, c: r["stats"][c]["r10_skew"] - r["stats"]["Azure"]["r10_skew"],
        "log Fano ratio 0.25 s": lambda r, c: float(np.log(r["stats"][c]["fano_0.25"] / r["stats"]["Azure"]["fano_0.25"])),
        "log Fano ratio 10 s": lambda r, c: float(np.log(r["stats"][c]["fano_10"] / r["stats"]["Azure"]["fano_10"])),
        "log Fano ratio 60 s": lambda r, c: float(np.log(r["stats"][c]["fano_60"] / r["stats"]["Azure"]["fano_60"])),
        "diff ACF lag 1 s": lambda r, c: r["stats"][c]["acf_1"] - r["stats"]["Azure"]["acf_1"],
        "diff ACF lag 20 s": lambda r, c: r["stats"][c]["acf_20"] - r["stats"]["Azure"]["acf_20"],
        "log ratio run above 2 SD": lambda r, c: float(np.log(r["stats"][c]["run_above_2sd_mean_s"] / r["stats"]["Azure"]["run_above_2sd_mean_s"])),
        "diff top-5% persistence at 5 s": lambda r, c: r["stats"][c]["persist_top5_5"] - r["stats"]["Azure"]["persist_top5_5"],
    }  # fmt: skip
    out: dict[str, Any] = {}
    for cand in ("C1", "C2"):
        for s, rho in CELLS:
            cells = [
                c
                for c in validation["results"][cand]["queueing"]["cells"]
                if c["service_s"] == s and c["target_rho"] == rho
            ]
            thr = 0.01 * s
            y = [
                float(np.log(c["model"]["p99"] / c["azure"]["p99"]))
                if c["azure"]["p99"] >= thr and c["model"]["p99"] >= thr
                else float("nan")
                for c in cells
            ]
            rows = [by_hour[c["hour"]] for c in cells]
            out[f"{cand} s={s} rho={rho}"] = {
                "median_p99_ratio": float(np.exp(np.nanmedian(y))),
                **{k: spearman([f(r, cand) for r in rows], y) for k, f in features.items()},
            }
    return out


def validation_breakdown() -> dict[str, Any]:
    v = json.loads(Path("analysis/results/validation-validation.json").read_text())
    out: dict[str, Any] = {}
    for cand in ("C1", "C2"):
        cells = v["results"][cand]["queueing"]["cells"]
        groups: dict[str, Callable[[dict[str, Any]], object]] = {
            "service_s": lambda c: c["service_s"],
            "target_rho": lambda c: c["target_rho"],
            "band": lambda c: common.band_of(c["rate"]),
        }
        res: dict[str, Any] = {}
        for gname, key in groups.items():
            for g in sorted({key(c) for c in cells}, key=str):
                cs = [c for c in cells if key(c) == g]
                s_thr = [(c, 0.01 * c["service_s"]) for c in cs]
                model = [c["model"]["p99"] / c["azure"]["p99"] for c, t in s_thr if c["azure"]["p99"] >= t and c["model"]["p99"] >= t]
                pois = [c["poisson"]["p99"] / c["azure"]["p99"] for c, t in s_thr if c["azure"]["p99"] >= t and c["poisson"]["p99"] >= t]
                label = f"{gname}={common.RATE_BANDS[int(str(g))] if gname == 'band' else g}"
                res[label] = {"cells": len(cs), "in_band": sum(c["verdict"]["in_band"] for c in cs),
                              "out_of_bounds": sum(c["verdict"]["out_of_bounds"] for c in cs),
                              "median_p99_ratio_model": float(np.median(model)) if model else None,
                              "median_p99_ratio_poisson": float(np.median(pois)) if pois else None}  # fmt: skip
        out[cand] = res
    return out


def main() -> None:
    thu = thursday(eligible_hours("validation"))
    train = training(eligible_hours("training"))
    record = {
        "splits": {"training": ["Fri", "Sat", "Sun", "Mon", "Tue"], "thursday": ["Thu"]},
        "wednesday_accessed": False,
        "raw_sha256": common.RAW_SHA256,
        "reference_sha256": common.sha256_file(REFERENCE),
        "seeds": {"stats": SEEDS_STATS, "block_shuffle": SEEDS_BLOCK, "sigma_reading": SEEDS_BIAS,
                  "surrogates": SURROGATE_SEED, "scheme": "validate.py's (10000*hour + seed)"},  # fmt: skip
        "validation_breakdown": validation_breakdown(),
        "thursday": thu,
        "training": train,
        "associations": associations(thu),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(record, indent=1, default=float) + "\n")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
