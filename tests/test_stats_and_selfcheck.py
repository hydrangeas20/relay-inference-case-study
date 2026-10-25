import math

import pytest

from relay.loadgen import selfcheck
from relay.loadgen.stats import bucket_width_at, histogram_quantile, percentiles


def test_percentiles_known_values() -> None:
    values = [float(v) for v in range(1, 101)]
    p = percentiles(values)
    assert p["p50"] == pytest.approx(50.5)
    assert p["p95"] == pytest.approx(95.05)
    assert p["p99"] == pytest.approx(99.01)


def test_percentiles_empty_is_none() -> None:
    assert percentiles([]) == {"p50": None, "p95": None, "p99": None}


def test_histogram_quantile_interpolates_within_bucket() -> None:
    # 10 samples in (0, 0.1], 10 in (0.1, 0.2]
    buckets = [(0.1, 10.0), (0.2, 20.0), (math.inf, 20.0)]
    assert histogram_quantile(0.5, buckets) == pytest.approx(0.1)
    assert histogram_quantile(0.75, buckets) == pytest.approx(0.15)


def test_histogram_quantile_in_inf_bucket_returns_highest_bound() -> None:
    buckets = [(0.1, 1.0), (math.inf, 10.0)]
    assert histogram_quantile(0.99, buckets) == pytest.approx(0.1)


def test_histogram_quantile_empty_is_none() -> None:
    assert histogram_quantile(0.5, [(0.1, 0.0), (math.inf, 0.0)]) is None


def test_bucket_width() -> None:
    assert bucket_width_at(0.15, [0.1, 0.2, math.inf]) == pytest.approx(0.1)
    assert bucket_width_at(0.05, [0.1, 0.2, math.inf]) == pytest.approx(0.1)
    assert math.isinf(bucket_width_at(5.0, [0.1, 0.2, math.inf]))


def _times(n: int, rate: float, stretch: float = 1.0) -> list[float]:
    return [i / rate * stretch for i in range(n)]


def test_selfcheck_valid_run() -> None:
    result = selfcheck.check(_times(100, 10), _times(100, 10, 1.01), [20.0] * 10)
    assert result.valid, result.reasons


def test_selfcheck_rate_shortfall_invalidates() -> None:
    result = selfcheck.check(_times(100, 10), _times(100, 10, 1.05), [20.0] * 10)
    assert not result.valid
    assert "below intended" in result.reasons[0]


def test_selfcheck_cpu_saturation_invalidates() -> None:
    result = selfcheck.check(_times(100, 10), _times(100, 10), [95.0] * 10)
    assert not result.valid
    assert any("CPU" in r for r in result.reasons)


def test_selfcheck_without_cpu_samples_is_invalid() -> None:
    result = selfcheck.check(_times(100, 10), _times(100, 10), [])
    assert not result.valid
