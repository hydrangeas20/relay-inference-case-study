"""Candidate D (D1) implementation, on synthetic data only (Cycle 2 preregistration, A3)."""

import importlib.util
import math
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "analysis"))
import cycle2_candidate_d as d  # noqa: E402
import cycle2_config as cfg  # noqa: E402
import cycle2_data  # noqa: E402
import cycle2_optimizer as opt  # noqa: E402
import cycle2_targets as tg  # noqa: E402
import cycle2_validation as val  # noqa: E402

THETA = opt.to_theta(0.44, -0.32, 9.2)


@pytest.fixture(autouse=True)
def _leave_cycle2_mode() -> Iterator[None]:
    yield
    cycle2_data.exit_cycle2_mode()


def _rows(days: tuple[str, ...] = ("d1", "d2", "d3"), rate: float = 4.0) -> list[dict[str, Any]]:
    rng = np.random.default_rng(7)
    rows = []
    for day in days:
        for h in range(3):
            t = np.sort(rng.uniform(0, 3600, rng.poisson(rate * 3600)))
            lam = np.full(36000, rate)
            rows.append({"day": day, "hour": h, "rate": len(t) / 3600, "band": 0, "times": t,
                         "lam": lam, "stats": tg.hour_components(t),
                         "out_of_range_fraction": 0.0})  # fmt: skip
    return rows


def test_model_is_the_cycle1_family_with_three_parameters() -> None:
    m = d.model_from_theta(THETA)
    assert (m.a, m.b, m.band_taus[0]) == pytest.approx((0.44, -0.32, 9.2))
    assert len(m.band_taus) == 1 and m.band_rates == (1.0,)
    assert (m.rate_min, m.rate_max) == cfg.RATE_RANGE_RPS
    lam = np.array([1.0, 50.0, 200.0])  # below, inside, above the frozen range
    np.testing.assert_allclose(m.sigma(lam, d.SCENARIO), 0.44 * lam**-0.32)
    np.testing.assert_allclose(m.tau(lam), 9.2)  # tau never extrapolates


def test_simulation_is_deterministic_per_seed_and_poisson_is_unmodulated() -> None:
    lam = np.full(36000, 5.0)
    m = d.model_from_theta(THETA)
    assert np.array_equal(d.simulate(m, lam, 11), d.simulate(m, lam, 11))
    assert not np.array_equal(d.simulate(m, lam, 11), d.simulate(m, lam, 12))
    counts = np.bincount((d.simulate(d.POISSON, lam, 3) // 1).astype(int), minlength=3600)
    assert counts.var() / counts.mean() == pytest.approx(1.0, abs=0.1)


def test_fit_specs_are_the_eleven_frozen_fits() -> None:
    specs = d.fit_specs()
    assert [s["fit"] for s in specs] == [
        "all",
        *cycle2_data.DEVELOPMENT_DAYS,
        *(f"without-band-{b}" for b in tg.BAND_LABELS),
    ]
    for s in specs[1:7]:
        assert s["fit"] not in s["training_days"] and len(s["training_days"]) == 5
    assert all(len(s["training_days"]) == 6 for s in (specs[0], *specs[7:]))
    assert [s["without_band"] for s in specs[7:]] == [0, 1, 2, 3]
    assert cycle2_data.HOLDOUT_DATE not in str(specs)


def test_fit_rows_respect_training_days_and_band_holdout() -> None:
    rows = _rows() + [{**r, "band": 2} for r in _rows(("d1",))]
    spec = {"fit": "x", "training_days": ["d1", "d2"], "without_band": 2}
    got = d.fit_rows(rows, spec)
    assert {r["day"] for r in got} == {"d1", "d2"} and {r["band"] for r in got} == {0}


def test_objective_uses_common_random_numbers() -> None:
    rows = _rows()
    full_sd = {b: {c: 0.05 for c in tg.REPORT_COMPONENTS} for b in tg.BAND_LABELS}
    fold = tg.fold_targets_and_weights(rows, ("d1", "d2", "d3"), full_sd)
    f = d.make_objective(rows, fold, "all")
    a, b = f(THETA), f(THETA)
    assert a == b and math.isfinite(a)
    other = f(opt.to_theta(0.8, -0.2, 20.0))
    assert math.isfinite(other) and other != a


def test_simulated_pooling_uses_every_hour_replicate() -> None:
    recs = [{"band": 0, "stats": {"s1_1": v, "acf_1": v}} for v in (0.01, 0.04, 0.09)]
    out = d.pooled_by_band(recs, ("s1_1", "acf_1"))
    assert out == {"3-10": {"s1_1": pytest.approx(0.2), "acf_1": pytest.approx(0.04)}}


def test_boundary_proximity() -> None:
    lo, hi = np.array(cfg.D_THETA_LOWER), np.array(cfg.D_THETA_UPPER)
    x = (lo + hi) / 2
    assert d.boundary_proximity(x)["near_bound"] == []
    x[1] = hi[1] - 0.005 * (hi[1] - lo[1])
    out = d.boundary_proximity(x)
    assert out["near_bound"] == ["b"] and out["distance_fraction"]["b"] == pytest.approx(0.005)


def test_preflight_passes_and_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    assert d.preflight()["pinned_sha256"]
    monkeypatch.setitem(d.PROCEDURE_SHA256, "analysis/cycle2_seeds.py", "0" * 64)
    with pytest.raises(RuntimeError, match="frozen artefacts"):
        d.preflight()


def test_procedure_pins_match_the_domain_freeze_test() -> None:
    spec = importlib.util.spec_from_file_location("dd", ROOT / "tests/test_cycle2_d_domain.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.PROCEDURE_SHA256 == d.PROCEDURE_SHA256


def test_queue_fold_shape_and_seed_streams() -> None:
    rows = _rows(("2024-05-10",), rate=3.5)[:1]
    out = d.queue_fold(THETA, "2024-05-10", rows)
    h = out["hours"][0]
    assert len(h["model"]) == len(h["poisson"]) == len(h["azure"]) == len(val.CELLS)
    m = val._as_array([h["model"]])
    assert m.shape == (1, 4, 2) and np.all(np.isfinite(m))
    assert d.queue_fold(THETA, "2024-05-10", rows) == out
