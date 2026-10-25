"""Audit of Azure's sub-second timestamp structure (ADR-0005 D2).

Usage: uv run python analysis/audit_subsecond.py [--split training]

Uses RAW timestamps (the structure is what de-jittering removes). Reports:
  - gaps under 1 ms vs what random (Poisson) arrivals at the same rate would give
  - exact duplicates and sub-10-microsecond gaps
  - uniformity of the microsecond digits
  - share of arrivals by 5 ms phase within each 250 ms interval
  - cluster sizes (chains of gaps < 1 ms) and whether clustered pairs look like duplicates
"""

from __future__ import annotations

import argparse
import json

import numpy as np

import common


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=("training", "validation"), default="training")
    args = parser.parse_args()
    data = common.load_split(args.split)
    t_all = np.concatenate([a["t"] for a in data.values()])
    gaps_all = np.concatenate([np.diff(a["t"]) for a in data.values()])
    micro = np.round((t_all % 1.0) * 1e6).astype(np.int64)
    phase = np.histogram(t_all % 0.25, bins=50, range=(0, 0.25))[0]

    by_band: dict[str, dict[str, float]] = {}
    for lo, hi in common.RATE_BANDS:
        obs, chance, same_ctx, other_ctx = [], [], [], []
        for arr in data.values():
            for h, th in common.hours(arr["t"]):
                rate = len(th) / 3600
                if not (lo <= rate < hi) or rate < common.MIN_ELIGIBLE_RATE:
                    continue
                g = np.diff(th)
                obs.append(np.mean(g < 1e-3))
                chance.append(1 - np.exp(-rate * 1e-3))
                edges = np.searchsorted(arr["t"], [h * 3600.0, (h + 1) * 3600.0])
                ctx = arr["ctx"][edges[0] : edges[1]]
                close = np.flatnonzero(g < 1e-3)
                far = np.flatnonzero(g >= 1e-2)
                same_ctx.append(np.mean(ctx[close] == ctx[close + 1]) if len(close) else np.nan)
                other_ctx.append(np.mean(ctx[far] == ctx[far + 1]) if len(far) else np.nan)
        if obs:
            by_band[f"{lo:g}-{hi:g}"] = {
                "hours": len(obs),
                "gap_lt_1ms": float(np.mean(obs)),
                "poisson_expected": float(np.mean(chance)),
                "identical_ctx_clustered_pairs": float(np.nanmean(same_ctx)),
                "identical_ctx_unclustered_pairs": float(np.nanmean(other_ctx)),
            }
    report = {
        "split": args.split,
        "timestamps": "raw",
        "rows": int(len(t_all)),
        "exactly_zero_gaps": float(np.mean(gaps_all == 0)),
        "gaps_lt_10us": float(np.mean(gaps_all < 1e-5)),
        "microsecond_last_digit_shares": (np.bincount(micro % 10, minlength=10) / len(micro)).round(4).tolist(),
        "share_in_last_50ms_of_250ms": float(np.mean((t_all % 0.25) >= 0.2)),
        "phase_250ms_5ms_bins_percent": (100 * phase / phase.sum()).round(2).tolist(),
        "by_band": by_band,
    }  # fmt: skip
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
