"""Checks on the traffic model and the traces it produces.

- Envelope (ADR-0004 1C): the model's weekday peak/trough ratio must fall inside the
  range of Azure's training weekdays. A plausibility check on one number, not evidence
  that Relay's daily shape matches Azure's.
- Burstiness: the rate-fluctuation statistic (relay.traffic.stats) of generated traffic.
- Prompt sizes (ADR-0005 D5): built prompt sizes against targets, with structurally
  below-minimum targets reported separately.
"""

from __future__ import annotations

import csv
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from relay.traces.schema import CompletionRequest, TraceRequest
from relay.traffic.model import TrafficModel
from relay.traffic.stats import WINDOWS_S, rate_cv2

# Weekdays in the training split (Fri 05-10, Mon 05-13, Tue 05-14); the reference
# hourly file holds training days only (preregistration §1).
WEEKDAYS = ("Fri", "Mon", "Tue")


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
    """Relative rate fluctuation per window (the shared estimator), as a dict."""
    cv2 = rate_cv2(times_s, int(duration_s), windows_s)
    return {w: float(np.sqrt(max(c, 0.0))) for w, c in zip(windows_s, cv2, strict=True)}


@dataclass
class PromptSizeReport:
    completions: int
    below_minimum: int
    below_minimum_fraction: float
    expected_mismatch: int  # built size differs from the generator's expected size
    below_minimum_inflation: list[float]  # built / target, for below-minimum targets


def prompt_size_report(
    requests: Sequence[TraceRequest], built_chars: dict[str, int], chars_per_token: float
) -> PromptSizeReport:
    comps = [r for r in requests if isinstance(r, CompletionRequest)]
    below = [r for r in comps if r.below_template_minimum]
    inflation = [
        built_chars[r.req_id] / (r.target_prompt_tokens * chars_per_token)
        for r in below
        if r.target_prompt_tokens and r.req_id in built_chars
    ]
    mismatch = sum(
        1
        for r in comps
        if r.req_id in built_chars and built_chars[r.req_id] != r.expected_prompt_chars
    )
    return PromptSizeReport(
        completions=len(comps),
        below_minimum=len(below),
        below_minimum_fraction=len(below) / len(comps) if comps else 0.0,
        expected_mismatch=mismatch,
        below_minimum_inflation=inflation,
    )


def ks_statistic(a: np.ndarray, b: np.ndarray) -> float:
    """Two-sample Kolmogorov-Smirnov distance."""
    a, b = np.sort(a), np.sort(b)
    v = np.concatenate([a, b])
    fa = np.searchsorted(a, v, side="right") / len(a)
    fb = np.searchsorted(b, v, side="right") / len(b)
    return float(np.max(np.abs(fa - fb)))


def ks_critical(n: int, m: int, c_alpha: float = 1.358) -> float:
    """Asymptotic two-sample KS critical value (c_alpha = 1.358 for alpha = 0.05)."""
    return float(c_alpha * np.sqrt((n + m) / (n * m)))
