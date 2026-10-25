"""Cycle 2 calibration targets, dispersion, tolerances and loss (Amendment 3, A3.1, A3.5, A3.7).

No candidate model here. Everything works on per-hour statistic dictionaries, so the
same code serves Azure development hours and, later, simulated hours.

Components (per hour):
  S1  s1_<W>   CV^2(W), W in {1, 2, 5, 10, 30, 60}; pooled as sqrt(max(median, 0))
  S2  acf_<L>  L in {1, 2, 5, 10, 20, 30, 60}
  S3  m<W>_<s> W in {10, 5}; s in skew, excess_kurtosis, zq0.01 ... zq0.999
  S4  persist_<top|bottom>_<L>, L in {1, 2, 5, 10, 20}
Every other component is pooled as the plain median.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from relay.traffic import higher_order as ho
from relay.traffic.stats import WINDOWS_S, rate_cv2

import cycle2_config as cfg

S1 = tuple(f"s1_{w}" for w in WINDOWS_S)
S2 = tuple(f"acf_{lag}" for lag in ho.ACF_LAGS_S)
S3_STATS = ("skew", "excess_kurtosis", *(f"zq{q}" for q in ho.MARGINAL_QUANTILES))
S3_10 = tuple(f"m10_{s}" for s in S3_STATS)
S3_5 = tuple(f"m5_{s}" for s in S3_STATS)
S4 = tuple(f"persist_{tail}_{lag}" for tail in ("top", "bottom") for lag in ho.PERSIST_LAGS_S)
TARGET_COMPONENTS = S1 + S2 + S3_10 + S4  # 30 per band: the loss
REPORT_COMPONENTS = TARGET_COMPONENTS + S3_5  # tolerances are reported for these too
BAND_LABELS = ("3-10", "10-30", "30-60", "60-120")


def hour_components(times_s: np.ndarray) -> dict[str, float]:
    """S1-S4 components of one hour (S5 excluded: diagnostic only)."""
    out = {f"s1_{w}": float(v) for w, v in zip(WINDOWS_S, rate_cv2(times_s, 3600), strict=True)}
    stats = ho.hour_statistics(times_s)
    out.update({k: stats[k] for k in REPORT_COMPONENTS if not k.startswith("s1_")})
    return out


def pool(values: Sequence[float], component: str) -> float:
    """Band pooling. S1: sqrt(max(median CV^2, 0)) exactly as Cycle 1 (A3.7)."""
    med = float(np.median(values))
    return math.sqrt(max(med, 0.0)) if component.startswith("s1_") else med


def pooled(rows: Sequence[Mapping[str, Any]], component: str) -> float:
    return pool([r["stats"][component] for r in rows], component)


def day_dispersion(
    rows: Sequence[Mapping[str, Any]], days: Sequence[str], band: int, component: str
) -> tuple[float | None, list[str]]:
    """Across-day SD (ddof=1) of daily band-pooled values, days with >= 3 band hours.

    None if fewer than 3 days qualify (the support rule).
    """
    qualifying, daily = [], []
    for d in days:
        hs = [r for r in rows if r["day"] == d and r["band"] == band]
        if len(hs) >= cfg.TOLERANCE_MIN_HOURS_PER_DAY:
            qualifying.append(d)
            daily.append(pooled(hs, component))
    if len(qualifying) < cfg.TOLERANCE_MIN_DAYS:
        return None, qualifying
    return float(np.std(daily, ddof=1)), qualifying


def full_development_sd(
    rows: Sequence[Mapping[str, Any]], days: Sequence[str]
) -> dict[str, dict[str, float | None]]:
    return {
        BAND_LABELS[b]: {c: day_dispersion(rows, days, b, c)[0] for c in REPORT_COMPONENTS}
        for b in range(len(BAND_LABELS))
    }


def reporting_tolerances(full_sd: Mapping[str, Mapping[str, float | None]]) -> dict[str, Any]:
    """A3.1: 2 x SD per component; no maxima, no floor."""
    return {
        band: {c: (None if sd is None else round(2 * sd, 6)) for c, sd in comps.items()}
        for band, comps in full_sd.items()
    }


def fold_targets_and_weights(
    rows: Sequence[Mapping[str, Any]],
    training_days: Sequence[str],
    full_sd: Mapping[str, Mapping[str, float | None]],
) -> dict[str, Any]:
    """A3.5: targets and 1/sd^2 weights from the fold's training days only.

    Fallback to the frozen full-development SD when fewer than 3 training days
    qualify; floor at 0.25 x the median over bands (post-fallback). Bands without any
    training hour are left out of the loss.
    """
    targets: dict[str, dict[str, float]] = {}
    sd: dict[str, dict[str, float]] = {}
    fallbacks: list[dict[str, Any]] = []
    excluded: list[str] = []
    for b, label in enumerate(BAND_LABELS):
        hs = [r for r in rows if r["day"] in training_days and r["band"] == b]
        if not hs:
            excluded.append(label)
            continue
        targets[label] = {c: pooled(hs, c) for c in TARGET_COMPONENTS}
        sd[label] = {}
        for c in TARGET_COMPONENTS:
            value, qualifying = day_dispersion(rows, training_days, b, c)
            if value is None:
                fb = full_sd[label][c]
                if fb is None:
                    raise ValueError(f"no frozen full-development SD for {label}/{c}")
                fallbacks.append({"band": label, "component": c, "qualifying_days": qualifying,
                                  "fallback_sd": fb})  # fmt: skip
                value = fb
            sd[label][c] = value
    floors = {
        c: cfg.SD_FLOOR_FRACTION * float(np.median([sd[band][c] for band in sd]))
        for c in TARGET_COMPONENTS
    }
    weights_sd = {
        band: {c: max(v, floors[c]) for c, v in comps.items()} for band, comps in sd.items()
    }
    return {"targets": targets, "sd": weights_sd, "floors": floors,
            "fallbacks": fallbacks, "excluded_bands": excluded}  # fmt: skip


def loss(
    simulated: Mapping[str, Mapping[str, float]], fold: Mapping[str, Any]
) -> tuple[float, dict[str, dict[str, float]]]:
    """Sum over bands and target components of ((sim - obs) / sd)^2. Non-finite -> inf."""
    residuals: dict[str, dict[str, float]] = {}
    total = 0.0
    for band, obs in fold["targets"].items():
        residuals[band] = {}
        for c in TARGET_COMPONENTS:
            z = (simulated[band][c] - obs[c]) / fold["sd"][band][c]
            residuals[band][c] = z
            total += z * z
    return (total if math.isfinite(total) else math.inf), residuals


def rate_range(rows: Sequence[Mapping[str, Any]]) -> tuple[float, float]:
    """A3.8: min and max mean rate of eligible hours (Cycle 1 §4 definition), unrounded."""
    rates = [float(r["rate"]) for r in rows]
    return min(rates), max(rates)


def frozen_dispersion() -> dict[str, Any]:
    """The Amendment 3 result file, after checking it against the frozen hash."""
    path = Path(__file__).resolve().parents[1] / cfg.DISPERSION_RESULT
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != cfg.DISPERSION_RESULT_SHA256:
        raise RuntimeError(f"{cfg.DISPERSION_RESULT} does not match its frozen hash")
    result: dict[str, Any] = json.loads(data)
    return result
