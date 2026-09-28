"""The burstiness statistic and its fitting functions.

One implementation, used by the analysis scripts (on Azure data), the traffic
checks (on generated traces) and the tests, so every comparison uses the same
estimator (docs/validation/phase-2-preregistration.md, "Estimator").

The statistic: for window W, the squared relative fluctuation of the *rate*,
with Poisson counting noise removed. Counts per second are compared with a
centred moving-average trend e; for windows of W seconds,
Z = (count - e) / e and CV_rate(W)^2 = mean(Z^2 - 1/e).
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

WINDOWS_S: tuple[int, ...] = (1, 2, 5, 10, 30, 60)
DETREND_WINDOW_S = 600


def per_second_counts(times_s: np.ndarray, duration_s: int) -> np.ndarray:
    counts = np.bincount(times_s.astype(int), minlength=duration_s)[:duration_s]
    return counts.astype(float)


def moving_average_trend(per_s: np.ndarray, k: int = DETREND_WINDOW_S) -> np.ndarray:
    """Centred k-second moving average, padding each end with its edge value."""
    k = min(k, len(per_s))
    pad = np.pad(per_s, (k // 2, k - k // 2 - 1), mode="edge")
    trend: np.ndarray = np.convolve(pad, np.ones(k) / k, mode="valid")
    return trend


def rate_cv2(
    times_s: np.ndarray,
    duration_s: int,
    windows_s: Sequence[int] = WINDOWS_S,
    k: int = DETREND_WINDOW_S,
) -> np.ndarray:
    """Squared relative rate fluctuation per window (Poisson noise removed). Can be < 0."""
    per_s = per_second_counts(times_s, duration_s)
    trend = moving_average_trend(per_s, k)
    out = []
    for w in windows_s:
        n = duration_s // w
        c = per_s[: n * w].reshape(n, w).sum(axis=1)
        e = trend[: n * w].reshape(n, w).sum(axis=1)
        ok = e > 0
        out.append(float(np.mean(((c[ok] - e[ok]) / e[ok]) ** 2 - 1.0 / e[ok])))
    return np.array(out)


def ou_shape(windows_s: np.ndarray, tau_s: float) -> np.ndarray:
    """Window-averaging factor for a rate with exponential autocorrelation (time tau)."""
    x = np.asarray(windows_s, dtype=float) / tau_s
    shape: np.ndarray = 2.0 * (x - 1.0 + np.exp(-x)) / x**2
    return shape


TAU_GRID_S = np.geomspace(0.1, 600.0, 2000)


def fit_sigma_tau(
    cv2: np.ndarray, windows_s: Sequence[int] = WINDOWS_S
) -> tuple[float, float, float]:
    """Least-squares fit in log space of cv2(W) = sigma^2 * ou_shape(W, tau).

    Returns (sigma, tau_s, log-space SSE). sigma^2 has a closed form for each tau.
    """
    w = np.asarray(windows_s, dtype=float)
    obs = np.log(np.clip(cv2, 1e-12, None))
    best = (np.inf, 0.0, 0.0)
    for tau in TAU_GRID_S:
        shape = np.log(ou_shape(w, tau))
        log_s2 = float(np.mean(obs - shape))
        err = float(np.sum((obs - log_s2 - shape) ** 2))
        if err < best[0]:
            best = (err, log_s2, float(tau))
    err, log_s2, tau = best
    return float(np.sqrt(np.exp(log_s2))), tau, err


def fit_shared_tau(
    curves: Sequence[np.ndarray], windows_s: Sequence[int] = WINDOWS_S
) -> tuple[list[float], float]:
    """Fit several cv2 curves with one shared tau and a sigma per curve (log-space LSQ)."""
    w = np.asarray(windows_s, dtype=float)
    logs = [np.log(np.clip(c, 1e-12, None)) for c in curves]
    best: tuple[float, list[float], float] = (np.inf, [], 0.0)
    for tau in TAU_GRID_S:
        shape = np.log(ou_shape(w, tau))
        sigmas, err = [], 0.0
        for obs in logs:
            log_s2 = float(np.mean(obs - shape))
            err += float(np.sum((obs - log_s2 - shape) ** 2))
            sigmas.append(float(np.sqrt(np.exp(log_s2))))
        if err < best[0]:
            best = (err, sigmas, float(tau))
    return best[1], best[2]


def fit_power_law(
    rates: Sequence[float], sigmas: Sequence[float], weights: Sequence[float]
) -> tuple[float, float]:
    """Weighted least squares of log(sigma) = log(a) + b*log(rate). Returns (a, b)."""
    x = np.log(np.asarray(rates, dtype=float))
    y = np.log(np.asarray(sigmas, dtype=float))
    wt = np.asarray(weights, dtype=float)
    b, log_a = np.polyfit(x, y, 1, w=np.sqrt(wt))
    return float(np.exp(log_a)), float(b)
