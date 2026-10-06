"""Bounded Nelder-Mead procedure for Candidate D (Cycle 2 preregistration, Amendment 3)."""

import math
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "analysis"))
import cycle2_optimizer as opt  # noqa: E402

LO = np.array([-3.0, -1.0, -2.0])
HI = np.array([2.0, 0.5, 6.0])
C1 = np.array([-0.8, -0.3, 2.2])


def quad(centre: np.ndarray):  # type: ignore[no-untyped-def]
    return lambda x: float(np.sum((np.asarray(x) - centre) ** 2))


def test_frozen_settings() -> None:
    assert opt.BUDGET == 300 and opt.STARTS == 8
    assert (opt.REFLECT, opt.EXPAND, opt.CONTRACT, opt.SHRINK) == (1.0, 2.0, 0.5, 0.5)
    assert opt.SIMPLEX_STEP_FRACTION == 0.10 and opt.FTOL == opt.XTOL == 1e-4
    assert len(opt.UNIT_DESIGN) == 7 and len(set(opt.UNIT_DESIGN)) == 7


def test_start_design_maps_to_bounds_and_appends_cycle1() -> None:
    s = opt.starts(LO, HI, C1)
    assert len(s) == 8
    np.testing.assert_allclose(s[0], (LO + HI) / 2)
    np.testing.assert_allclose(s[1], [LO[0] + 0.1 * (HI[0] - LO[0]), -0.25, 2.0])
    np.testing.assert_allclose(s[6], [-0.5, -0.25, LO[2] + 0.9 * (HI[2] - LO[2])])
    np.testing.assert_array_equal(s[7], C1)
    for x in s:
        assert np.all(x >= LO) and np.all(x <= HI)


def test_starts_require_cycle1_inside_bounds() -> None:
    with pytest.raises(ValueError):
        opt.starts(LO, HI, np.array([5.0, -0.3, 2.2]))
    with pytest.raises(ValueError):
        opt.starts(HI, LO, C1)


def test_transform_roundtrip() -> None:
    p = opt.from_theta(opt.to_theta(0.44, -0.32, 9.2))
    assert p == pytest.approx({"a": 0.44, "b": -0.32, "tau_s": 9.2})


def test_converges_on_interior_quadratic() -> None:
    centre = np.array([0.3, -0.2, 1.0])
    r = opt.fit(quad(centre), LO, HI, opt.starts(LO, HI, C1))
    assert r["valid"] and r["termination"] == "converged"
    np.testing.assert_allclose(r["best_theta"], centre, atol=1e-2)
    assert r["evaluations"] <= 300 and r["evaluations"] == len(r["history"])
    assert [h["phase"] for h in r["history"][:8]] == [f"start_{i}" for i in range(1, 9)]


def test_optimum_outside_bounds_is_clipped() -> None:
    centre = np.array([5.0, -0.2, 1.0])  # beyond upper bound on log a
    r = opt.fit(quad(centre), LO, HI, opt.starts(LO, HI, C1))
    assert all(np.all(np.array(h["theta"]) <= HI) for h in r["history"])
    assert all(np.all(np.array(h["theta"]) >= LO) for h in r["history"])
    assert r["best_theta"][0] == pytest.approx(HI[0], abs=1e-2)


def test_budget_counts_starts_and_is_hard() -> None:
    calls = []

    def f(x: np.ndarray) -> float:
        calls.append(1)
        return float(np.sum(np.sin(5 * x)) + 1e-9 * len(calls))  # never settles fast

    r = opt.fit(f, LO, HI, opt.starts(LO, HI, C1), budget=20)
    assert r["termination"] == "budget_exhausted"
    assert r["evaluations"] == len(calls) == 20


def test_nonfinite_and_exceptions_become_inf_and_are_recorded() -> None:
    def f(x: np.ndarray) -> float:
        if x[1] > 0.0:
            raise RuntimeError("bad")
        if x[0] > 1.0:
            return math.nan
        return float(np.sum(x**2))

    r = opt.fit(f, LO, HI, opt.starts(LO, HI, C1))
    bad = [h for h in r["history"] if not math.isfinite(h["f"])]
    assert r["invalid_evaluations"] == len(bad) >= 1
    assert any(h["error"] and "RuntimeError" in h["error"] for h in bad)
    assert math.isfinite(r["best_objective"]) and r["valid"]


def test_no_finite_start_is_invalid() -> None:
    r = opt.fit(lambda x: math.inf, LO, HI, opt.starts(LO, HI, C1))
    assert not r["valid"] and r["termination"] == "no_finite_start"
    assert r["evaluations"] == 8 and r["best_theta"] is None and r["chosen_start"] is None


def test_ties_choose_lower_start_number() -> None:
    s = opt.starts(LO, HI, C1)
    r = opt.fit(lambda x: 1.0, LO, HI, s, budget=8)
    assert r["chosen_start"] == 1
    target = s[3]
    r = opt.fit(lambda x: 0.0 if np.allclose(x, target) or np.allclose(x, s[7]) else 1.0,
                LO, HI, s, budget=8)  # fmt: skip
    assert r["chosen_start"] == 4


def test_exactly_eight_starts_required() -> None:
    with pytest.raises(ValueError):
        opt.fit(quad(C1), LO, HI, opt.starts(LO, HI, C1)[:7])


def test_deterministic() -> None:
    a = opt.fit(quad(np.array([0.1, 0.1, 0.1])), LO, HI, opt.starts(LO, HI, C1))
    b = opt.fit(quad(np.array([0.1, 0.1, 0.1])), LO, HI, opt.starts(LO, HI, C1))
    assert a["history"] == b["history"]
