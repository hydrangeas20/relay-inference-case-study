"""Checks that the traffic model and the traces it produces match their references.

- Envelope vs Azure (decision 1C): the model's weekday peak/trough ratio must fall
  inside the range Azure's Mon-Thu days show.
- Burstiness (decision 2C): a generated trace's short-timescale rate fluctuation
  must match the Azure fit it was generated from.
- Sizes (decision 3B): how often a completion prompt falls short of its target
  because no corpus file is long enough.
"""

from __future__ import annotations

import csv
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from relay.traces.schema import CompletionRequest, TraceRequest
from relay.traffic.model import TrafficModel

WEEKDAYS = ("Mon", "Tue", "Wed", "Thu")  # Fri is a partial day in the Azure sample
DETREND_WINDOW_S = 600
WINDOWS_S = (1, 2, 5, 10, 30, 60)


@dataclass
class EnvelopeCheck:
    passed: bool
    model_peak_to_trough: float
    azure_weekday_min: float
    azure_weekday_max: float
    model_peak_hour_utc: int
    model_trough_hour_utc: int


def azure_weekday_ratios(hourly_csv: Path) -> list[float]:
    with hourly_csv.open() as f:
        rows = list(csv.DictReader(f))
    ratios = []
    for d in range(len(rows) // 24):
        day = rows[d * 24 : (d + 1) * 24]
        if day[0]["weekday"] in WEEKDAYS:
            counts = [int(r["requests"]) for r in day]
            ratios.append(max(counts) / min(counts))
    return ratios


def check_envelope(model: TrafficModel, hourly_csv: Path) -> EnvelopeCheck:
    hours = model.hourly_shape()
    ratio = float(hours.max() / hours.min())
    azure = azure_weekday_ratios(hourly_csv)
    return EnvelopeCheck(
        passed=min(azure) <= ratio <= max(azure),
        model_peak_to_trough=round(ratio, 2),
        azure_weekday_min=round(min(azure), 2),
        azure_weekday_max=round(max(azure), 2),
        model_peak_hour_utc=int(hours.argmax()),
        model_trough_hour_utc=int(hours.argmin()),
    )


def rate_cv_by_window(
    times_s: np.ndarray, duration_s: float, windows_s: Sequence[int] = WINDOWS_S
) -> dict[int, float]:
    """Relative fluctuation of the arrival *rate* per window size, Poisson noise removed.

    Same estimator as analysis/azure_traffic.py: counts per second against a
    10-minute moving-average trend; for window W, Var((c - e) / e) - 1/e.
    """
    n_s = int(duration_s)
    per_s = np.bincount(times_s.astype(int), minlength=n_s)[:n_s].astype(float)
    k = min(DETREND_WINDOW_S, n_s)
    pad = np.pad(per_s, (k // 2, k - k // 2 - 1), mode="edge")
    trend = np.convolve(pad, np.ones(k) / k, mode="valid")
    out = {}
    for w in windows_s:
        n = n_s // w
        c = per_s[: n * w].reshape(n, w).sum(axis=1)
        e = trend[: n * w].reshape(n, w).sum(axis=1)
        ok = e > 0
        z2 = ((c[ok] - e[ok]) / e[ok]) ** 2 - 1.0 / e[ok]
        out[w] = float(np.sqrt(max(np.mean(z2), 0.0)))
    return out


def prompt_shortfall(requests: Sequence[TraceRequest]) -> float:
    """Fraction of completions whose prefix couldn't reach its target length."""
    comps = [r for r in requests if isinstance(r, CompletionRequest)]
    if not comps:
        return 0.0
    short = sum(r.cursor < r.prefix_chars for r in comps)
    return short / len(comps)
