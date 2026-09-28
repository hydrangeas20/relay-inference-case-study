"""Rate-dependent burstiness (ADR-0005 D1; preregistration §5).

The expected rate lambda(t) is multiplied by m(t) = exp(s_t X_t - s_t^2 / 2), with
s_t^2 = ln(1 + sigma(lambda(t))^2) and X a unit-variance Ornstein-Uhlenbeck process
whose correlation time tau(lambda(t)) may vary with the rate.

Inside Azure's observed range (training days), sigma follows the fitted power law
sigma(lambda) = a * lambda^b (AZURE-DERIVED). Outside it, burstiness is uncertain and
comes from a named scenario:

  edge     sigma and tau held at the nearest range boundary (canonical default)
  poisson  sigma = 0 (low-burst sensitivity)
  trend    a * lambda^b extrapolated (PROJECTED; never an empirical estimate)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np

Scenario = Literal["edge", "poisson", "trend"]
SCENARIOS: tuple[Scenario, ...] = ("edge", "poisson", "trend")
CANDIDATES = ("C1", "C2")


class OutOfRangeError(ValueError):
    """The trace's rate leaves the observed range and no scenario was named."""


@dataclass(frozen=True)
class BurstinessModel:
    name: str
    a: float
    b: float
    band_rates: tuple[float, ...]
    band_taus: tuple[float, ...]
    rate_min: float
    rate_max: float

    def in_range(self, lam: np.ndarray) -> np.ndarray:
        lam = np.asarray(lam, dtype=float)
        result: np.ndarray = (lam >= self.rate_min) & (lam <= self.rate_max)
        return result

    def _power(self, lam: np.ndarray) -> np.ndarray:
        result: np.ndarray = self.a * np.power(np.maximum(lam, 1e-9), self.b)
        return result

    def sigma(self, lam: np.ndarray, scenario: Scenario | None) -> np.ndarray:
        lam = np.asarray(lam, dtype=float)
        inside = self.in_range(lam)
        if not inside.all() and scenario is None:
            raise OutOfRangeError(
                f"expected rate leaves the observed range [{self.rate_min}, {self.rate_max}] rps; "
                f"name a burstiness scenario ({', '.join(SCENARIOS)})"
            )
        if scenario == "edge" or scenario is None:
            return self._power(np.clip(lam, self.rate_min, self.rate_max))
        if scenario == "poisson":
            return np.where(inside, self._power(lam), 0.0)
        if scenario == "trend":
            return self._power(lam)
        raise ValueError(f"unknown scenario {scenario!r}")

    def tau(self, lam: np.ndarray) -> np.ndarray:
        """Correlation time. Constant for C1; interpolated in log-rate for C2, held at ends."""
        lam = np.clip(np.asarray(lam, dtype=float), self.rate_min, self.rate_max)
        if len(set(self.band_taus)) == 1:
            return np.full(lam.shape, self.band_taus[0])
        x = np.log(np.asarray(self.band_rates))
        y = np.log(np.asarray(self.band_taus))
        result: np.ndarray = np.exp(np.interp(np.log(lam), x, y))
        return result

    def out_of_range_fraction(self, lam: np.ndarray) -> float:
        return float(1.0 - self.in_range(lam).mean()) if len(lam) else 0.0


def load_candidate(reference: dict[str, Any], name: str) -> BurstinessModel:
    if name not in CANDIDATES:
        raise ValueError(f"unknown burstiness candidate {name!r}")
    c = reference["candidates"][name]
    lo, hi = reference["observed_range_rps"]
    return BurstinessModel(
        name=name,
        a=float(c["a"]),
        b=float(c["b"]),
        band_rates=tuple(float(x) for x in c["band_rates"]),
        band_taus=tuple(float(x) for x in c["band_taus"]),
        rate_min=float(lo),
        rate_max=float(hi),
    )


def modulation(
    model: BurstinessModel,
    lam: np.ndarray,
    dt_s: float,
    rng: np.random.Generator,
    scenario: Scenario | None,
) -> np.ndarray:
    """Multiplier per bin (mean 1) for expected rates `lam` (requests/s, one per bin)."""
    lam = np.asarray(lam, dtype=float)
    sig = model.sigma(lam, scenario)
    s = np.sqrt(np.log1p(sig * sig))
    a = np.exp(-dt_s / model.tau(lam))
    eps = rng.standard_normal(len(lam))
    x = np.empty(len(lam))
    x[0] = rng.standard_normal()
    c = np.sqrt(1.0 - a * a)
    for i in range(1, len(lam)):  # unit-variance AR(1): exact OU discretisation
        x[i] = a[i] * x[i - 1] + c[i] * eps[i]
    result: np.ndarray = np.exp(s * x - s * s / 2.0)
    return result


def constant_modulation(
    sigma: float, tau: float, n_bins: int, dt_s: float, rng: np.random.Generator
) -> np.ndarray:
    """Fixed-parameter multiplier (used by tests and the estimator-recovery check)."""
    s = math.sqrt(math.log1p(sigma * sigma))
    a = math.exp(-dt_s / tau)
    eps = rng.standard_normal(n_bins)
    x = np.empty(n_bins)
    x[0] = rng.standard_normal()
    c = math.sqrt(1.0 - a * a)
    for i in range(1, n_bins):
        x[i] = a * x[i - 1] + c * eps[i]
    result: np.ndarray = np.exp(s * x - s * s / 2.0)
    return result
