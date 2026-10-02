import sys
from pathlib import Path

import numpy as np
import pytest

from relay.traffic import higher_order as ho
from relay.traffic.generate import BIN_S, cox_arrivals
from relay.traffic.model import load_model
from relay.traffic.stats import moving_average_trend, per_second_counts

ROOT = Path(__file__).resolve().parents[1]
MODEL = load_model(ROOT / "traffic" / "relay.toml")


def _bursty_hour(rate: float, seed: int) -> np.ndarray:
    lam = np.full(int(3600 / BIN_S), rate)
    return cox_arrivals(MODEL, lam, np.random.default_rng(seed), None, 3600.0)


def _poisson_hour(rate: float, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return np.sort(rng.uniform(0, 3600, rng.poisson(rate * 3600)))


def test_matches_cycle_1_diagnostic_estimators() -> None:
    """S2, S3 (skew, kurtosis, sd at 10 s), S4 and S5 exceedance equal Cycle 1's definitions."""
    sys.path.insert(0, str(ROOT / "analysis"))
    import diagnose_queueing as cycle1  # noqa: PLC0415

    t = _bursty_hour(20.0, 3)
    trend = moving_average_trend(per_second_counts(t, 3600))
    old = cycle1.arrival_stats(t, trend)
    new = ho.hour_statistics(t)
    pairs = {f"acf_{lag}": f"acf_{lag}" for lag in ho.ACF_LAGS_S}
    pairs |= {"m10_skew": "r10_skew", "m10_sd": "r10_sd"}
    pairs |= {"m10_excess_kurtosis": "r10_excess_kurtosis"}
    pairs |= {f"persist_top_{lag}": f"persist_top5_{lag}" for lag in ho.PERSIST_LAGS_S}
    pairs |= {f"persist_bottom_{lag}": f"persist_bottom5_{lag}" for lag in ho.PERSIST_LAGS_S}
    for k in ("frac", "runs_per_hour", "run_mean_s", "area_mean"):
        pairs[f"s5_exceed_0.25_{k}"] = f"exceed_0.25_{k}"
        pairs[f"s5_exceed_0.4_{k}"] = f"exceed_0.4_{k}"
    for new_key, old_key in pairs.items():
        assert new[new_key] == pytest.approx(old[old_key], rel=1e-9, abs=1e-12), new_key


def test_poisson_has_no_dependence_and_little_shape() -> None:
    s = ho.hour_statistics(_poisson_hour(30.0, 1))
    # Standard error of a sample autocorrelation over 3,600 s is about 0.017; allow 4 SE.
    assert all(abs(s[f"acf_{lag}"]) < 0.07 for lag in ho.ACF_LAGS_S)
    assert s["persist_top_20"] == pytest.approx(0.05, abs=0.02)
    assert abs(s["m10_skew"]) < 0.2 and abs(s["m10_excess_kurtosis"]) < 0.4


def test_bursty_traffic_shows_dependence_and_right_skew() -> None:
    s = ho.hour_statistics(_bursty_hour(20.0, 2))
    assert s["acf_1"] > 0.2 and s["acf_5"] > s["acf_30"]
    assert s["persist_top_5"] > 0.1
    assert s["m10_skew"] > 0  # the log-normal link is right-skewed


def test_standardised_quantiles_are_ordered_and_centred() -> None:
    s = ho.hour_statistics(_bursty_hour(20.0, 4))
    q = [s[f"m10_zq{p}"] for p in ho.MARGINAL_QUANTILES]
    assert q == sorted(q) and q[0] < 0 < q[-1]


def test_runs_lengths_and_areas() -> None:
    mask = np.array([0, 1, 1, 0, 1, 0, 0, 1, 1, 1], dtype=bool)
    excess = np.arange(10, dtype=float)
    lengths, areas = ho._runs(mask, excess)
    assert lengths.tolist() == [2, 1, 3]
    assert areas.tolist() == [1 + 2, 4, 7 + 8 + 9]


def test_fluid_backlog_by_hand() -> None:
    # c = ceil(2 * 1.0 / 0.8) = 3 servers; per-second work 5, 1, 0 -> backlog 2, 0, 0.
    per_s = np.array([5.0, 1.0, 0.0] * 100)
    assert ho.fluid_backlog_p99(per_s, 2.0, 1.0, 0.8) == pytest.approx(2.0)
    assert ho.fluid_backlog_p99(np.ones(300), 2.0, 1.0, 0.8) == 0.0


def test_s5_is_marked_diagnostic_only() -> None:
    keys = ho.hour_statistics(_poisson_hour(10.0, 5)).keys()
    s5 = [k for k in keys if ho.is_diagnostic_only(k)]
    assert s5 and all(k.startswith("s5_") for k in s5)
    calibration = [k for k in keys if k.startswith(("acf_", "m", "persist_"))]
    assert calibration and not any(ho.is_diagnostic_only(k) for k in calibration)


def test_band_pooled_is_elementwise_median() -> None:
    pooled = ho.band_pooled([{"a": 1.0, "b": 5.0}, {"a": 3.0, "b": 4.0}, {"a": 2.0, "b": 9.0}])
    assert pooled == {"a": 2.0, "b": 5.0}
