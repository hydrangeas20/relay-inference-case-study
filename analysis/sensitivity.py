"""Preregistered sensitivity report (docs/validation/phase-2-preregistration.md §9). Descriptive.

Usage: uv run python analysis/sensitivity.py

Runs after Thursday selection (reads analysis/results/validation-validation.json):
  - for the §8 GPU window and a day trace (peak 20 rps): fraction of time outside the
    observed range, and sigma over time under edge / poisson / trend
  - queue metrics for the day trace's out-of-range hours under each scenario
    (s in {0.2, 1.0} s, rho = 0.8, 20 seeds)
  - the clustered variant vs raw Thursday timestamps: gaps < 1 ms, mean cluster size,
    and 250 ms phase uniformity
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from relay.config import get_settings
from relay.traffic.burstiness import SCENARIOS, load_candidate
from relay.traffic.clustering import cluster
from relay.traffic.generate import BIN_S, cox_arrivals
from relay.traffic.model import load_model
from relay.traffic.queueing import queue_metrics, servers_for

import common
import validation_config as cfg

SELECTION = Path("analysis/results/validation-validation.json")
OUT = Path("analysis/results/sensitivity.json")


def implied_mean_cluster_size(t: np.ndarray, rate: float, gap_s: float = 0.001) -> float:
    """Mean cluster size implied by excess sub-millisecond gaps: the definition used for
    the clustering reference (analysis/azure_traffic.py): 1 / (1 - excess)."""
    observed = float(np.mean(np.diff(t) < gap_s))
    chance = 1.0 - float(np.exp(-rate * gap_s))
    excess = max(0.0, (observed - chance) / (1.0 - chance))
    return 1.0 / (1.0 - excess)


def main() -> None:
    cfg.require_resolved()
    if not SELECTION.exists():
        raise SystemExit("run analysis/validate.py first: sensitivity uses the selected candidate")
    chosen = json.loads(SELECTION.read_text())["selection"]["selected"]
    settings = get_settings()
    model = load_model(settings.traffic_model)
    ref = json.loads(Path("traffic/reference/azure_code_burstiness.json").read_text())
    bm = load_candidate(ref, chosen)
    scale_day = cfg.SENSITIVITY_DAY_TRACE["peak_rps"] / model.peak_interactive_rps()
    t = (np.arange(int(86_400 / BIN_S)) + 0.5) * BIN_S
    lam_day = sum(model.interactive_rate_rps(t).values()) * scale_day
    h, m = str(cfg.FIDELITY_TRACE["start"]).split(":")
    t0 = int(h) * 3600 + int(m) * 60
    tw = t0 + (np.arange(int(float(cfg.FIDELITY_TRACE["minutes"]) * 60 / BIN_S)) + 0.5) * BIN_S
    lam_win = sum(model.interactive_rate_rps(tw).values()) * (
        float(cfg.FIDELITY_TRACE["peak_rps"]) / model.peak_interactive_rps()
    )
    report: dict[str, object] = {
        "candidate": chosen,
        "observed_range_rps": [bm.rate_min, bm.rate_max],
    }
    report["gpu_window"] = {"out_of_range_fraction": bm.out_of_range_fraction(lam_win)}
    hourly = lam_day.reshape(24, -1).mean(axis=1)
    report["day_trace"] = {
        "out_of_range_fraction": bm.out_of_range_fraction(lam_day),
        "hourly_rate": hourly.round(3).tolist(),
        "sigma_by_scenario_hourly": {s: bm.sigma(hourly, s).round(4).tolist() for s in SCENARIOS},  # type: ignore[arg-type]
    }
    out_hours = [i for i, r in enumerate(hourly) if not (bm.rate_min <= r <= bm.rate_max)]
    queue: dict[str, object] = {}
    for hr in out_hours:
        lam = lam_day[hr * int(3600 / BIN_S) : (hr + 1) * int(3600 / BIN_S)]
        for scenario in SCENARIOS:
            for s in cfg.SERVICE_TIMES_S:
                c = servers_for(float(lam.mean()), s, 0.8)
                ms = [queue_metrics(cox_arrivals(SimpleNamespace(burstiness=bm), lam,  # type: ignore[arg-type]
                                                 np.random.default_rng(seed), scenario, 3600.0), c, s, 3600.0)
                      for seed in cfg.SEEDS]  # fmt: skip
                queue[f"hour {hr:02d} {scenario} s={s}"] = {
                    "servers": c, "p95": float(np.median([x.p95 for x in ms])),
                    "p99": float(np.median([x.p99 for x in ms]))}  # fmt: skip
    report["day_trace_out_of_range_queueing"] = queue

    thu = common.load_split("validation")["2024-05-16"]["t"]
    clustered = []
    for hr, th in common.hours(thu):
        rate = len(th) / 3600
        if rate < common.MIN_ELIGIBLE_RATE:
            continue
        lam = np.full(int(3600 / BIN_S), rate)
        base = cox_arrivals(
            SimpleNamespace(burstiness=bm), lam, np.random.default_rng(hr), "edge", 3600.0
        )  # type: ignore[arg-type]
        ct, _ = cluster(
            model.clustering, base, np.full(len(base), rate), np.random.default_rng(hr), 3600.0
        )
        clustered.append({
            "hour": hr, "rate": round(rate, 2),
            "azure_raw_gap_lt_1ms": float(np.mean(np.diff(th) < 1e-3)),
            "clustered_gap_lt_1ms": float(np.mean(np.diff(ct) < 1e-3)),
            "canonical_gap_lt_1ms": float(np.mean(np.diff(base) < 1e-3)),
            "azure_raw_last_50ms_share": float(np.mean((th % 0.25) >= 0.2)),
            "clustered_last_50ms_share": float(np.mean((ct % 0.25) >= 0.2)),
            "azure_raw_mean_cluster_size": implied_mean_cluster_size(th, rate),
            "clustered_mean_cluster_size": implied_mean_cluster_size(ct, rate),
            "canonical_mean_cluster_size": implied_mean_cluster_size(base, rate),
        })  # fmt: skip
    report["clustered_vs_raw_thursday"] = clustered
    OUT.write_text(json.dumps(report, indent=1, default=float) + "\n")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
