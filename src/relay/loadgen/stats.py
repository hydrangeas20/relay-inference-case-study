"""Percentiles and histogram quantiles."""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np

DEFAULT_QS = (50.0, 95.0, 99.0)


def percentiles(
    values: Sequence[float], qs: Sequence[float] = DEFAULT_QS
) -> dict[str, float | None]:
    """p50/p95/p99 of raw samples (linear interpolation). None when there are no samples."""
    if not values:
        return {f"p{q:g}": None for q in qs}
    arr = np.asarray(values, dtype=float)
    return {f"p{q:g}": float(np.percentile(arr, q)) for q in qs}


def histogram_quantile(q: float, buckets: Sequence[tuple[float, float]]) -> float | None:
    """Quantile estimate from cumulative histogram buckets, Prometheus-style.

    `buckets` are (upper_bound, cumulative_count) pairs including +Inf. Interpolates
    linearly inside the bucket containing the rank. If the rank lands in the +Inf
    bucket the highest finite bound is returned (the true value is only known to be
    above it). Returns None for an empty histogram.
    """
    if not 0.0 <= q <= 1.0:
        raise ValueError("q must be in [0, 1]")
    ordered = sorted(buckets)
    if not ordered or not math.isinf(ordered[-1][0]):
        raise ValueError("buckets must include +Inf")
    total = ordered[-1][1]
    if total <= 0:
        return None
    rank = q * total
    prev_bound, prev_count = 0.0, 0.0
    for bound, count in ordered:
        if count >= rank:
            if math.isinf(bound):
                return prev_bound
            if count == prev_count:
                return bound
            return prev_bound + (bound - prev_bound) * (rank - prev_count) / (count - prev_count)
        prev_bound, prev_count = bound, count
    return prev_bound


def bucket_width_at(value: float, bounds: Sequence[float]) -> float:
    """Width of the histogram bucket containing `value`: the estimate's resolution there."""
    finite = sorted(b for b in bounds if not math.isinf(b))
    lower = 0.0
    for b in finite:
        if value <= b:
            return b - lower
        lower = b
    return math.inf
