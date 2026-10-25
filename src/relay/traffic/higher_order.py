"""Higher-order traffic statistics S2-S5 (Cycle 2 preregistration, section "Statistics").

One implementation, used on Azure development data and on generated traffic alike,
so every comparison runs both through the same estimator (indirect inference: Poisson
counting noise and detrending affect both sides identically).

All statistics are computed per hour from arrival times in [0, duration) and the
centred 600 s moving-average trend of that hour's per-second counts (the S1 trend,
`relay.traffic.stats.moving_average_trend`). With n_t the count in second t and
e_t the trend, the 1 s relative rate is z_t = n_t / e_t - 1.

S2  autocorrelation of z at lags ACF_LAGS_S (time dependence shape)
S3  marginal shape of the W-second relative rate r_W = sum(n) / sum(e) - 1 over
    non-overlapping windows, W in MARGINAL_WINDOWS_S: skewness, excess kurtosis,
    and standardised quantiles (q - mean) / sd at MARGINAL_QUANTILES
S4  persistence of extreme states: with z smoothed by a centred 3 s moving average,
    P(in top 5% at t + L | in top 5% at t), and the same for the bottom 5%,
    at L in PERSIST_LAGS_S
S5  DIAGNOSTIC ONLY (never a calibration target or selection input): exceedance of
    the 5 s-smoothed z above EXCEED_THRESHOLDS (fraction of time, runs per hour,
    mean run length, mean area per run), and the p99 of a per-second fluid backlog
    B_t = max(0, B_{t-1} + n_t * s - c) for the queue cells in FLUID_CELLS.

These definitions match the Cycle 1 diagnosis (analysis/diagnose_queueing.py) where
the two overlap; the test suite checks that. S3's quantiles are standardised here
(Cycle 1 reported raw quantiles), so marginal *shape* is separated from scale (S1).
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence

import numpy as np

from relay.traffic.stats import moving_average_trend, per_second_counts

ACF_LAGS_S: tuple[int, ...] = (1, 2, 5, 10, 20, 30, 60)
MARGINAL_WINDOWS_S: tuple[int, ...] = (5, 10)
MARGINAL_QUANTILES: tuple[float, ...] = (0.01, 0.05, 0.95, 0.99, 0.999)
PERSIST_LAGS_S: tuple[int, ...] = (1, 2, 5, 10, 20)
PERSIST_SMOOTH_S = 3
PERSIST_TAIL = 0.05
EXCEED_THRESHOLDS: tuple[float, ...] = (0.25, 0.4)
EXCEED_SMOOTH_S = 5
FLUID_CELLS: tuple[tuple[float, float], ...] = ((0.2, 0.6), (0.2, 0.8), (1.0, 0.6), (1.0, 0.8))


def relative_rate(per_s: np.ndarray, trend: np.ndarray) -> np.ndarray:
    """z_t = n_t / e_t - 1."""
    z: np.ndarray = per_s / trend - 1.0
    return z


def acf(z: np.ndarray, lags: Sequence[int] = ACF_LAGS_S) -> dict[int, float]:
    """S2: sample autocorrelation of z (mean removed) at the given lags."""
    zc = z - z.mean()
    var = float(np.mean(zc * zc))
    return {lag: float(np.mean(zc[:-lag] * zc[lag:]) / var) for lag in lags}


def window_marginal(
    per_s: np.ndarray,
    trend: np.ndarray,
    window_s: int,
    quantiles: Sequence[float] = MARGINAL_QUANTILES,
) -> dict[str, float]:
    """S3: skewness, excess kurtosis and standardised quantiles of r_W."""
    n = len(per_s) // window_s
    r = (
        per_s[: n * window_s].reshape(n, window_s).sum(1)
        / trend[: n * window_s].reshape(n, window_s).sum(1)
        - 1.0
    )
    d = r - r.mean()
    sd = float(np.sqrt(np.mean(d * d)))
    out = {
        "sd": sd,
        "skew": float(np.mean(d**3) / sd**3),
        "excess_kurtosis": float(np.mean(d**4) / sd**4 - 3.0),
    }
    for q in quantiles:
        out[f"zq{q}"] = float((np.quantile(r, q) - r.mean()) / sd)
    return out


def _smooth(z: np.ndarray, k: int) -> np.ndarray:
    out: np.ndarray = np.convolve(z, np.ones(k) / k, mode="same")
    return out


def persistence(
    z: np.ndarray,
    lags: Sequence[int] = PERSIST_LAGS_S,
    smooth_s: int = PERSIST_SMOOTH_S,
    tail: float = PERSIST_TAIL,
) -> dict[str, float]:
    """S4: P(still in the top / bottom `tail` fraction after each lag)."""
    r = _smooth(z, smooth_s)
    hi, lo = r > np.quantile(r, 1 - tail), r < np.quantile(r, tail)
    out = {}
    for lag in lags:
        out[f"top_{lag}"] = float(np.mean(hi[lag:][hi[:-lag]]))
        out[f"bottom_{lag}"] = float(np.mean(lo[lag:][lo[:-lag]]))
    return out


def _runs(mask: np.ndarray, excess: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Lengths and summed `excess` of each maximal run of True in `mask`."""
    m = np.concatenate([[False], mask, [False]])
    starts = np.flatnonzero(~m[:-1] & m[1:])
    ends = np.flatnonzero(m[:-1] & ~m[1:])
    cum = np.concatenate([[0.0], np.cumsum(np.where(mask, excess, 0.0))])
    return ends - starts, cum[ends] - cum[starts]


def exceedance(
    z: np.ndarray,
    thresholds: Iterable[float] = EXCEED_THRESHOLDS,
    smooth_s: int = EXCEED_SMOOTH_S,
) -> dict[str, float]:
    """S5 (diagnostic only): time above each threshold and its runs."""
    r = _smooth(z, smooth_s)
    out = {}
    for thr in thresholds:
        lengths, areas = _runs(r > thr, r - thr)
        out[f"{thr}_frac"] = float(np.mean(r > thr))
        out[f"{thr}_runs_per_hour"] = float(len(lengths)) * 3600.0 / len(r)
        out[f"{thr}_run_mean_s"] = float(lengths.mean()) if len(lengths) else 0.0
        out[f"{thr}_area_mean"] = float(areas.mean()) if len(areas) else 0.0
    return out


def fluid_backlog_p99(per_s: np.ndarray, rate: float, service_s: float, rho: float) -> float:
    """S5 (diagnostic only): p99 of B_t = max(0, B_{t-1} + n_t * s - c), c = ceil(rate*s/rho)."""
    c = max(1, math.ceil(rate * service_s / rho))
    b, out = 0.0, np.empty(len(per_s))
    for i, n in enumerate(per_s):
        b = max(0.0, b + float(n) * service_s - c)
        out[i] = b
    return float(np.percentile(out, 99))


def hour_statistics(times_s: np.ndarray, duration_s: int = 3600) -> dict[str, float]:
    """All S2-S5 statistics for one hour, as a flat dict.

    Keys: acf_<lag>, m<W>_<stat>, persist_<top|bottom>_<lag> (S2-S4, calibration
    candidates) and s5_* (diagnostic only).
    """
    per_s = per_second_counts(times_s, duration_s)
    trend = moving_average_trend(per_s)
    z = relative_rate(per_s, trend)
    rate = len(times_s) / duration_s
    out: dict[str, float] = {}
    out.update({f"acf_{k}": v for k, v in acf(z).items()})
    for w in MARGINAL_WINDOWS_S:
        out.update({f"m{w}_{k}": v for k, v in window_marginal(per_s, trend, w).items()})
    out.update({f"persist_{k}": v for k, v in persistence(z).items()})
    out.update({f"s5_exceed_{k}": v for k, v in exceedance(z).items()})
    for s, rho in FLUID_CELLS:
        out[f"s5_fluid_p99_{s}_{rho}"] = fluid_backlog_p99(per_s, rate, s, rho)
    return out


def is_diagnostic_only(key: str) -> bool:
    """S5 keys may never enter calibration loss or candidate selection."""
    return key.startswith("s5_")


def band_pooled(hours: Sequence[dict[str, float]]) -> dict[str, float]:
    """Element-wise median across a rate band's hours (as S1's pooled band curve)."""
    return {k: float(np.median([h[k] for h in hours])) for k in hours[0]}
