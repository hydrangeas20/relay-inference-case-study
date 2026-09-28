import numpy as np
import pytest

from relay.traffic.burstiness import constant_modulation
from relay.traffic.stats import fit_power_law, fit_shared_tau, fit_sigma_tau, ou_shape, rate_cv2


def _cox(rate: float, sigma: float, tau: float, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    lam = np.full(36_000, rate * 0.1)
    if sigma > 0:
        lam = lam * constant_modulation(sigma, tau, 36_000, 0.1, rng)
    bins = np.repeat(np.arange(36_000), rng.poisson(lam))
    return np.sort((bins + rng.random(len(bins))) * 0.1)


def test_estimator_recovers_known_parameters() -> None:
    fits = [
        fit_sigma_tau(np.clip(rate_cv2(_cox(80, 0.16, 9.0, s), 3600), 1e-12, None))
        for s in range(4)
    ]
    sigma = np.mean([f[0] for f in fits])
    tau = np.mean([f[1] for f in fits])
    assert sigma == pytest.approx(0.16, abs=0.02)
    assert tau == pytest.approx(9.0, abs=3.0)


def test_estimator_is_about_zero_on_poisson() -> None:
    cv2 = rate_cv2(_cox(30, 0.0, 1.0, 0), 3600)
    assert np.all(np.abs(cv2) < 5e-4)


def test_fit_recovers_exact_curve() -> None:
    w = np.array([1, 2, 5, 10, 30, 60], dtype=float)
    curve = 0.2**2 * ou_shape(w, 7.0)
    sigma, tau, err = fit_sigma_tau(curve)
    assert sigma == pytest.approx(0.2, rel=0.01)
    assert tau == pytest.approx(7.0, rel=0.02)
    assert err < 1e-4


def test_shared_tau_and_power_law() -> None:
    w = np.array([1, 2, 5, 10, 30, 60], dtype=float)
    curves = [s**2 * ou_shape(w, 9.0) for s in (0.25, 0.18, 0.12)]
    sigmas, tau = fit_shared_tau(curves)
    assert tau == pytest.approx(9.0, rel=0.02)
    assert sigmas == pytest.approx([0.25, 0.18, 0.12], rel=0.01)
    a, b = fit_power_law([1.0, 10.0, 100.0], [0.4, 0.2, 0.1], [1, 1, 1])
    assert b == pytest.approx(np.log10(0.5) / 1.0 * 1.0, abs=0.01)
    assert a == pytest.approx(0.4, rel=0.01)
