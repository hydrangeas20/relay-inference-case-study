import json
from pathlib import Path

import numpy as np
import pytest

from relay.traffic.burstiness import BurstinessModel, OutOfRangeError, load_candidate, modulation
from relay.traffic.generate import BIN_S, cox_arrivals
from relay.traffic.model import load_model
from relay.traffic.stats import rate_cv2

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = json.loads((ROOT / "traffic" / "reference" / "azure_code_burstiness.json").read_text())
C1 = load_candidate(REFERENCE, "C1")
C2 = load_candidate(REFERENCE, "C2")


def test_reference_is_training_only() -> None:
    assert REFERENCE["derived_from"]["split"] == "training"
    assert REFERENCE["derived_from"]["days"] == ["Fri", "Sat", "Sun", "Mon", "Tue"]
    assert REFERENCE["observed_range_rps"] == [3.2, 82.83]


def test_sigma_is_the_power_law_inside_the_range() -> None:
    lam = np.array([3.2, 10.0, 50.0, 82.83])
    for m in (C1, C2):
        assert np.allclose(m.sigma(lam, None), m.a * lam**m.b)
        assert np.all(np.diff(m.sigma(lam, None)) < 0)  # falls with rate


def test_out_of_range_needs_a_scenario() -> None:
    with pytest.raises(OutOfRangeError):
        C1.sigma(np.array([1.0, 10.0]), None)
    with pytest.raises(OutOfRangeError):
        C1.sigma(np.array([500.0]), None)


def test_scenarios_only_change_out_of_range_values() -> None:
    lam = np.array([1.0, 10.0, 2434.0])
    edge = C1.sigma(lam, "edge")
    pois = C1.sigma(lam, "poisson")
    trend = C1.sigma(lam, "trend")
    inside = C1.a * 10.0**C1.b
    assert edge[1] == pois[1] == trend[1] == pytest.approx(inside)
    assert edge[0] == pytest.approx(C1.a * C1.rate_min**C1.b)
    assert edge[2] == pytest.approx(C1.a * C1.rate_max**C1.b)
    assert pois[0] == pois[2] == 0.0
    assert trend[2] == pytest.approx(C1.a * 2434.0**C1.b)
    assert trend[2] < edge[2]


def test_c1_tau_is_constant_and_c2_interpolates() -> None:
    lam = np.array([1.0, 7.7, 15.2, 48.5, 70.8, 500.0])
    assert len(set(np.round(C1.tau(lam), 9))) == 1
    t2 = C2.tau(lam)
    assert t2[0] == pytest.approx(C2.band_taus[0])  # held below the first band rate
    assert t2[-1] == pytest.approx(C2.band_taus[-1])  # and above the last
    assert t2[2] == pytest.approx(C2.band_taus[1], rel=0.01)


def test_modulation_has_mean_one_and_the_fitted_spread() -> None:
    rate = 20.0
    m = modulation(C1, np.full(400_000, rate), 0.5, np.random.default_rng(0), None)
    assert m.mean() == pytest.approx(1.0, abs=0.01)
    assert m.std() == pytest.approx(float(C1.sigma(np.array([rate]), None)[0]), rel=0.05)
    lag = round(float(C1.tau(np.array([rate]))[0]) / 0.5)
    x = np.log(m) - np.log(m).mean()
    assert float(np.mean(x[:-lag] * x[lag:]) / np.var(x)) == pytest.approx(np.exp(-1), abs=0.05)


def test_poisson_scenario_gives_no_modulation_out_of_range() -> None:
    m = modulation(C1, np.full(1000, 1.0), BIN_S, np.random.default_rng(0), "poisson")
    assert np.allclose(m, 1.0)


@pytest.mark.parametrize("band", [1, 2])
def test_generated_traffic_reproduces_training_band_curve(band: int) -> None:
    """In-sample: the generator implements the fit (not out-of-sample validation)."""
    model = load_model(ROOT / "traffic" / "relay.toml")
    b = REFERENCE["bands"][band]
    lam = np.full(int(3600 / BIN_S), float(b["median_rate"]))
    curves = [
        rate_cv2(cox_arrivals(model, lam, np.random.default_rng(s), None, 3600.0), 3600)
        for s in range(3)
    ]
    generated = np.sqrt(np.clip(np.mean(curves, axis=0), 0, None))
    tolerance = REFERENCE["tolerances"][("3-10", "10-30", "30-60")[band]]["tolerance"]
    assert np.max(np.abs(generated - np.asarray(b["pooled_cv"]))) <= tolerance


def test_holdout_fits_exclude_their_band() -> None:
    fits = REFERENCE["band_holdout_fits"]
    assert set(fits) == {"without 3-10", "without 10-30", "without 30-60", "without 60-120"}
    for fit in fits.values():
        assert len(fit["bands"]) == 3


def test_model_rejects_unknown_candidate() -> None:
    with pytest.raises(ValueError):
        load_candidate(REFERENCE, "C3")
    assert isinstance(C1, BurstinessModel)
