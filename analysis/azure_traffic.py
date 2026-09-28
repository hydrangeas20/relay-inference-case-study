"""Derive the traffic model's reference data from Azure's trace (training days only).

Usage: uv run python analysis/azure_traffic.py

Reads the SHA-256-verified raw trace (see analysis/README.md), training split only
(Fri 05-10 .. Tue 05-14; the Wednesday holdout is never read), and writes to
traffic/reference/:

  azure_code_hourly.csv        requests per UTC hour, training days
  azure_code_sizes.csv         20,000 sampled (context, generated) token pairs, training days
  azure_code_burstiness.json   per-band statistics, candidate fits C1/C2, observed range,
                               out-of-sample tolerances (preregistration §3-§6)
  azure_code_clustering.json   sub-second clustering statistics for the clustered
                               sensitivity variant (ADR-0005 D2), from raw timestamps

Source: Azure LLM inference trace 2024, CC-BY 4.0.
  Stojkovic et al., "DynamoLLM: Designing LLM Inference Clusters for Performance
  and Energy Efficiency", HPCA 2025. https://github.com/Azure/AzurePublicDataset
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from relay.traffic.stats import (
    DETREND_WINDOW_S,
    WINDOWS_S,
    fit_power_law,
    fit_shared_tau,
    fit_sigma_tau,
    rate_cv2,
)

import common

OUT = Path("traffic/reference")
SIZE_SAMPLE = 20_000
SIZE_SEED = 20240510
CLUSTER_GAP_S = 1e-3


def eligible_hours(data: dict[str, dict[str, np.ndarray]]) -> list[dict[str, object]]:
    rows = []
    for day, arr in data.items():
        t = common.dejitter(arr["t"])
        for h, th in common.hours(t):
            rate = len(th) / 3600
            band = common.band_of(rate)
            if rate >= common.MIN_ELIGIBLE_RATE and band is not None:
                rows.append({"day": day, "hour": h, "rate": rate, "band": band,
                             "cv2": rate_cv2(th, 3600)})  # fmt: skip
    return rows


def pooled(rows: list[dict[str, object]]) -> tuple[np.ndarray, float, int]:
    cv2 = np.median(np.array([r["cv2"] for r in rows]), axis=0)
    return cv2, float(np.median([r["rate"] for r in rows])), len(rows)


def fit_candidates(rows: list[dict[str, object]], bands: list[int]) -> dict[str, object]:
    """Fit C1 and C2 on the given bands' hours (preregistration §5)."""
    curves, rates, counts = [], [], []
    for b in bands:
        cv2, rate, n = pooled([r for r in rows if r["band"] == b])
        curves.append(cv2)
        rates.append(rate)
        counts.append(n)
    shared_sigmas, shared_tau = fit_shared_tau(curves)
    a1, b1 = fit_power_law(rates, shared_sigmas, counts)
    indiv = [fit_sigma_tau(c) for c in curves]
    a2, b2 = fit_power_law(rates, [s for s, _, _ in indiv], counts)
    return {
        "bands": bands,
        "band_rates": rates,
        "C1": {
            "a": a1,
            "b": b1,
            "band_rates": rates,
            "band_taus": [shared_tau] * len(bands),
            "band_sigmas": shared_sigmas,
        },  # fmt: skip
        "C2": {
            "a": a2,
            "b": b2,
            "band_rates": rates,
            "band_taus": [t for _, t, _ in indiv],
            "band_sigmas": [s for s, _, _ in indiv],
        },  # fmt: skip
    }


def tolerances(rows: list[dict[str, object]]) -> dict[str, object]:
    """2 x max-over-windows of the day-to-day SD of daily pooled curves (§6.1)."""

    def spread(band_filter: object) -> dict[str, object] | None:
        daily = []
        days = []
        for day in common.TRAINING:
            hs = [r for r in rows if r["day"] == day and band_filter(r)]  # type: ignore[operator]
            if len(hs) >= 3:
                daily.append(np.sqrt(np.clip(np.median([r["cv2"] for r in hs], axis=0), 0, None)))
                days.append(common.DAYS[day])
        if len(daily) < 2:
            return None
        sd = np.std(np.array(daily), axis=0, ddof=1)
        return {
            "days": days,
            "sd": sd.round(5).tolist(),
            "tolerance": round(2 * float(sd.max()), 4),
        }

    out: dict[str, object] = {}
    for b, (lo, hi) in enumerate(common.RATE_BANDS):
        out[f"{lo:g}-{hi:g}"] = spread(lambda r, b=b: r["band"] == b)
    out["30-120 (O2 option a)"] = spread(lambda r: 30 <= r["rate"] < 120)
    return out


def clustering(data: dict[str, dict[str, np.ndarray]]) -> dict[str, object]:
    """Excess sub-millisecond clustering per band, from RAW timestamps (not de-jittered)."""
    per_band: dict[int, list[tuple[float, float]]] = {b: [] for b in range(len(common.RATE_BANDS))}
    within: list[np.ndarray] = []
    for arr in data.values():
        for _, th in common.hours(arr["t"]):
            rate = len(th) / 3600
            band = common.band_of(rate)
            if rate < common.MIN_ELIGIBLE_RATE or band is None:
                continue
            gaps = np.diff(th)
            per_band[band].append((rate, float(np.mean(gaps < CLUSTER_GAP_S))))
            within.append(gaps[gaps < CLUSTER_GAP_S])
    bands = []
    for b, vals in per_band.items():
        rate = float(np.median([v[0] for v in vals]))
        observed = float(np.median([v[1] for v in vals]))
        chance = 1.0 - float(np.exp(-rate * CLUSTER_GAP_S))
        excess = max(0.0, (observed - chance) / (1.0 - chance))
        bands.append({"rate_range": list(common.RATE_BANDS[b]), "median_rate": rate,
                      "hours": len(vals), "gap_lt_1ms_observed": observed,
                      "gap_lt_1ms_chance": chance, "mean_cluster_size": 1.0 / (1.0 - excess)})  # fmt: skip
    gaps_all = np.concatenate(within)
    return {
        "source": "raw timestamps (not de-jittered), training days",
        "cluster_gap_s": CLUSTER_GAP_S,
        "model": "each arrival becomes a cluster parent with probability 1/m; clusters have "
        "geometric size with mean m; gaps inside a cluster are drawn from the quantiles below. "
        "No 250 ms periodic structure.",
        "bands": bands,
        "within_cluster_gap_quantiles_s": np.quantile(gaps_all, np.linspace(0, 1, 101)).tolist(),
    }


def main() -> None:
    data = common.load_split("training")
    OUT.mkdir(parents=True, exist_ok=True)

    with (OUT / "azure_code_hourly.csv").open("w") as f:
        f.write("hour_utc,weekday,requests\n")
        for day, arr in data.items():
            counts = np.bincount((arr["t"] // 3600).astype(int), minlength=24)[:24]
            for h, n in enumerate(counts):
                f.write(f"{day}T{h:02d}:00Z,{common.DAYS[day]},{int(n)}\n")

    ctx = np.concatenate([a["ctx"] for a in data.values()])
    gen = np.concatenate([a["gen"] for a in data.values()])
    rng = np.random.default_rng(SIZE_SEED)
    idx = np.sort(rng.choice(len(ctx), size=SIZE_SAMPLE, replace=False))
    with (OUT / "azure_code_sizes.csv").open("w") as f:
        f.write("context_tokens,generated_tokens\n")
        f.writelines(f"{int(c)},{int(g)}\n" for c, g in zip(ctx[idx], gen[idx], strict=True))

    rows = eligible_hours(data)
    rates = [r["rate"] for r in rows]
    band_table = []
    for b, (lo, hi) in enumerate(common.RATE_BANDS):
        cv2, rate, n = pooled([r for r in rows if r["band"] == b])
        band_table.append({"range_rps": [lo, hi], "hours": n, "median_rate": rate,
                           "pooled_cv2": cv2.tolist(),
                           "pooled_cv": np.sqrt(np.clip(cv2, 0, None)).tolist()})  # fmt: skip
    holdouts = {
        f"without {lo:g}-{hi:g}": fit_candidates(rows, [x for x in range(4) if x != b])
        for b, (lo, hi) in enumerate(common.RATE_BANDS)
    }
    burst = {
        "format": 2,
        "derived_from": {
            "raw_sha256": common.RAW_SHA256,
            "split": "training",
            "days": [common.DAYS[d] for d in common.TRAINING],
            "timestamps": "de-jittered within 250 ms (seed 20260928)",
        },
        "estimator": {"windows_s": list(WINDOWS_S), "detrend_window_s": DETREND_WINDOW_S},
        "eligible_hours": len(rows),
        "observed_range_rps": [round(min(rates), 2), round(max(rates), 2)],
        "bands": band_table,
        "candidates": fit_candidates(rows, [0, 1, 2, 3]),
        "band_holdout_fits": holdouts,
        "tolerances": tolerances(rows),
    }
    (OUT / "azure_code_burstiness.json").write_text(json.dumps(burst, indent=2) + "\n")
    (OUT / "azure_code_clustering.json").write_text(json.dumps(clustering(data), indent=2) + "\n")
    c = burst["candidates"]
    print(json.dumps({"observed_range_rps": burst["observed_range_rps"],
                      "C1": {k: c["C1"][k] for k in ("a", "b", "band_taus")},
                      "C2": {k: c["C2"][k] for k in ("a", "b", "band_taus")},
                      "tolerances": burst["tolerances"]}, indent=1, default=str))  # fmt: skip


if __name__ == "__main__":
    main()
