"""Cycle 2 targets, dispersion, tolerances and loss (Cycle 2 preregistration, Amendment 3)."""

import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "analysis"))
import cycle2_targets as tg  # noqa: E402

DAYS = ("d1", "d2", "d3", "d4", "d5", "d6")


def _row(day: str, band: int, value: float, rate: float = 20.0) -> dict[str, Any]:
    return {"day": day, "band": band, "rate": rate,
            "stats": {c: value for c in tg.REPORT_COMPONENTS}}  # fmt: skip


def _rows(spec: dict[str, dict[int, list[float]]]) -> list[dict[str, Any]]:
    return [_row(d, b, v) for d, bands in spec.items() for b, vs in bands.items() for v in vs]


def test_component_lists() -> None:
    assert len(tg.TARGET_COMPONENTS) == 30
    assert len(tg.S1) == 6 and len(tg.S2) == 7 and len(tg.S3_10) == 7 and len(tg.S4) == 10
    assert len(tg.REPORT_COMPONENTS) == 37
    assert not any(c.startswith("s5_") for c in tg.REPORT_COMPONENTS)
    assert not set(tg.S3_5) & set(tg.TARGET_COMPONENTS)


def test_s1_pooling_is_sqrt_of_median_not_median_of_sqrt() -> None:
    v = [0.01, 0.04, 0.25, 0.36]  # median CV^2 = 0.145
    assert tg.pool(v, "s1_10") == pytest.approx(math.sqrt(0.145))
    assert tg.pool(v, "s1_10") != pytest.approx(float(np.median(np.sqrt(v))))
    assert tg.pool([-0.2, -0.1, 0.0], "s1_1") == 0.0
    assert tg.pool(v, "acf_1") == pytest.approx(0.145)


def test_hour_components_on_poisson_hour() -> None:
    rng = np.random.default_rng(0)
    t = np.sort(rng.uniform(0, 3600, 20 * 3600))
    c = tg.hour_components(t)
    assert set(c) == set(tg.REPORT_COMPONENTS)
    assert abs(c["acf_1"]) < 0.05


def test_day_dispersion_support_rule() -> None:
    rows = _rows({"d1": {0: [1.0] * 3}, "d2": {0: [2.0] * 3}, "d3": {0: [4.0] * 2}})
    sd, q = tg.day_dispersion(rows, DAYS, 0, "acf_1")
    assert sd is None and q == ["d1", "d2"]
    rows += _rows({"d3": {0: [4.0]}})
    sd, q = tg.day_dispersion(rows, DAYS, 0, "acf_1")
    assert q == ["d1", "d2", "d3"] and sd == pytest.approx(np.std([1, 2, 4], ddof=1))


def test_reporting_tolerances_are_twice_sd_per_component_without_max() -> None:
    full = {"3-10": {"acf_1": 0.1, "m10_skew": 0.5, "persist_top_1": None}}
    assert tg.reporting_tolerances(full) == {
        "3-10": {"acf_1": 0.2, "m10_skew": 1.0, "persist_top_1": None}
    }


def _full_sd(value: float = 0.5) -> dict[str, dict[str, float]]:
    return {b: {c: value for c in tg.REPORT_COMPONENTS} for b in tg.BAND_LABELS}


def test_fold_uses_training_days_only_and_records_fallbacks() -> None:
    spec = {d: {0: [float(i)] * 3, 3: [10.0 + i] * 3} for i, d in enumerate(DAYS)}
    spec["d6"][0] = [1000.0] * 3  # held out: must not influence anything
    spec["d4"].pop(3)  # band 3 then has only 2 qualifying training days (d2, d3) ...
    spec["d5"].pop(3)
    spec["d1"][3] = [10.0] * 2  # ... d1 below 3 hours
    rows = _rows(spec)
    fold = tg.fold_targets_and_weights(rows, DAYS[:5], _full_sd(0.7))
    assert fold["targets"]["3-10"]["acf_1"] == pytest.approx(2.0)  # median of 0..4
    assert fold["sd"]["3-10"]["acf_1"] == pytest.approx(np.std(range(5), ddof=1))
    assert fold["excluded_bands"] == ["10-30", "30-60"]
    fb = [f for f in fold["fallbacks"] if f["band"] == "60-120"]
    assert len(fb) == 30 and all(f["fallback_sd"] == 0.7 for f in fb)
    assert fb[0]["qualifying_days"] == ["d2", "d3"]
    assert all(f["band"] == "60-120" for f in fold["fallbacks"])
    # changing the held-out day changes nothing
    rows2 = [r if r["day"] != "d6" else _row("d6", r["band"], -5.0) for r in rows]
    assert tg.fold_targets_and_weights(rows2, DAYS[:5], _full_sd(0.7)) == fold


def test_fallback_without_frozen_value_raises() -> None:
    rows = _rows({"d1": {0: [1.0] * 3}})
    full = _full_sd()
    full["3-10"]["acf_1"] = None  # type: ignore[assignment]
    with pytest.raises(ValueError):
        tg.fold_targets_and_weights(rows, ("d1",), full)


def test_floor_is_quarter_of_median_over_bands() -> None:
    spec = {d: {0: [0.0] * 3, 1: [float(i)] * 3, 2: [10.0 * i] * 3} for i, d in enumerate(DAYS)}
    fold = tg.fold_targets_and_weights(_rows(spec), DAYS[:5], _full_sd())
    s1 = np.std(range(5), ddof=1)
    assert fold["floors"]["acf_1"] == pytest.approx(0.25 * s1)  # median of {0, s1, 10 s1}
    assert fold["sd"]["3-10"]["acf_1"] == pytest.approx(0.25 * s1)  # 0 raised to floor
    assert fold["sd"]["30-60"]["acf_1"] == pytest.approx(10 * s1)


def test_loss_and_residuals() -> None:
    fold = {"targets": {"3-10": {c: 1.0 for c in tg.TARGET_COMPONENTS}},
            "sd": {"3-10": {c: 0.5 for c in tg.TARGET_COMPONENTS}}}  # fmt: skip
    sim = {"3-10": {c: 2.0 for c in tg.TARGET_COMPONENTS}}
    total, res = tg.loss(sim, fold)
    assert total == pytest.approx(30 * 4.0) and res["3-10"]["acf_1"] == pytest.approx(2.0)
    sim["3-10"]["acf_1"] = math.nan
    assert tg.loss(sim, fold)[0] == math.inf


def test_rate_range() -> None:
    rows = [_row("d1", 0, 0.0, rate=3.014), _row("d2", 3, 0.0, rate=101.236)]
    assert tg.rate_range(rows) == (3.014, 101.236)
