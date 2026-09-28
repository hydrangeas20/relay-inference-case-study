"""The queue used by the preregistered queueing test (preregistration §7).

c identical servers, first come first served, fixed service time s, empty at t = 0.
With identical fixed service times and FIFO order, request i starts service at
max(a_i, start_{i-c} + s): the server it gets is the one freed by request i - c.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import numpy as np


def fifo_start_times(arrivals: np.ndarray, c: int, s: float) -> np.ndarray:
    if c < 1 or s <= 0:
        raise ValueError("need c >= 1 and s > 0")
    a = np.asarray(arrivals, dtype=float)
    if np.any(np.diff(a) < 0):
        raise ValueError("arrivals must be sorted")
    start = np.empty(len(a))
    for i in range(len(a)):
        start[i] = a[i] if i < c else max(a[i], start[i - c] + s)
    return start


@dataclass
class QueueMetrics:
    p50: float
    p95: float
    p99: float
    fraction_waiting: float
    peak_waiting: int
    worst_60s_mean_wait: float
    utilisation: float


def queue_metrics(arrivals: np.ndarray, c: int, s: float, duration_s: float) -> QueueMetrics:
    a = np.asarray(arrivals, dtype=float)
    if len(a) == 0:
        return QueueMetrics(0.0, 0.0, 0.0, 0.0, 0, 0.0, 0.0)
    start = fifo_start_times(a, c, s)
    wait = start - a
    # Number waiting just after each arrival: earlier-or-equal arrivals not yet started.
    started_by = np.searchsorted(start, a, side="right")
    waiting = np.arange(1, len(a) + 1) - np.minimum(started_by, np.arange(1, len(a) + 1))
    window = (a // 60).astype(int)
    sums = np.bincount(window, weights=wait)
    counts = np.bincount(window)
    means = sums[counts > 0] / counts[counts > 0]
    p50, p95, p99 = (float(x) for x in np.percentile(wait, [50, 95, 99]))
    return QueueMetrics(
        p50=p50,
        p95=p95,
        p99=p99,
        fraction_waiting=float(np.mean(wait > 0)),
        peak_waiting=int(waiting.max()),
        worst_60s_mean_wait=float(means.max()),
        utilisation=len(a) * s / (c * duration_s),
    )


def servers_for(rate: float, s: float, rho: float) -> int:
    return max(1, math.ceil(rate * s / rho))


# ---- preregistered acceptance logic (§7) --------------------------------------------

BAND = (0.67, 1.5)
BOUNDS = (0.5, 2.0)
NEAR_ZERO = 0.01  # fraction of the service time


@dataclass
class MetricVerdict:
    agrees_near_zero: bool
    fails_near_zero: bool
    ratio: float | None  # model / Azure when neither side is near zero, or A > 0
    log_error: float  # 0 for near-zero agreement, inf for near-zero failure


def judge(model: float, azure: float, s: float) -> MetricVerdict:
    thr = NEAR_ZERO * s
    m_low, a_low = model < thr, azure < thr
    if m_low and a_low:
        return MetricVerdict(True, False, None, 0.0)
    ratio = model / azure if azure > 0 else None
    if m_low != a_low:
        return MetricVerdict(False, True, ratio, math.inf)
    assert ratio is not None
    return MetricVerdict(False, False, ratio, abs(math.log(ratio)))


def _out_of_bounds(mv: MetricVerdict, azure: float) -> bool:
    """Criterion 2: ratio outside 0.5-2.0, or a one-sided near-zero failure with A = 0."""
    if mv.fails_near_zero and azure == 0:
        return True
    if mv.agrees_near_zero or mv.ratio is None:
        return False
    return not (BOUNDS[0] <= mv.ratio <= BOUNDS[1])


@dataclass
class CellVerdict:
    in_band: bool  # criterion 1
    out_of_bounds: bool  # criterion 2 violation
    beats_poisson: bool | None  # criterion 3; None for a tie (excluded from denominator)


def judge_cell(
    model: dict[str, float], poisson: dict[str, float], azure: dict[str, float], s: float
) -> CellVerdict:
    in_band = True
    out = False
    m_err, p_err = [], []
    tie = True
    for key in ("p95", "p99"):
        mv = judge(model[key], azure[key], s)
        pv = judge(poisson[key], azure[key], s)
        if not mv.agrees_near_zero:
            ok = (
                (not mv.fails_near_zero) and mv.ratio is not None and BAND[0] <= mv.ratio <= BAND[1]
            )
            in_band &= ok
        out |= _out_of_bounds(mv, azure[key])
        m_err.append(mv.log_error)
        p_err.append(pv.log_error)
        tie &= mv.agrees_near_zero and pv.agrees_near_zero
    beats = None if tie else all(m < p for m, p in zip(m_err, p_err, strict=True))
    return CellVerdict(in_band=in_band, out_of_bounds=out, beats_poisson=beats)


@dataclass
class Acceptance:
    cells: int
    in_band: int
    out_of_bounds: int
    non_tie: int
    beats_poisson: int
    ties: int
    criterion_1: bool
    criterion_2: bool
    criterion_3: bool
    passed: bool


def accept(verdicts: list[CellVerdict]) -> Acceptance:
    n = len(verdicts)
    in_band = sum(v.in_band for v in verdicts)
    oob = sum(v.out_of_bounds for v in verdicts)
    non_tie = [v for v in verdicts if v.beats_poisson is not None]
    beats = sum(1 for v in non_tie if v.beats_poisson)
    c1 = n > 0 and in_band / n >= 0.8
    c2 = oob == 0
    c3 = bool(non_tie) and beats / len(non_tie) >= 0.8
    return Acceptance(n, in_band, oob, len(non_tie), beats, n - len(non_tie), c1, c2, c3,
                      c1 and c2 and c3)  # fmt: skip


def as_dict(obj: object) -> dict[str, object]:
    return asdict(obj)  # type: ignore[call-overload,no-any-return]
