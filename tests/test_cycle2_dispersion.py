"""Frozen Amendment 3 values: dispersion, S2-S4 tolerances, rate range (Cycle 2 prereg)."""

import json
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "analysis"))
import common  # noqa: E402
import cycle2_config as cfg  # noqa: E402
import cycle2_data  # noqa: E402
import cycle2_dispersion as disp  # noqa: E402
import cycle2_targets as tg  # noqa: E402

RESULT = tg.frozen_dispersion()  # raises if the file doesn't match the frozen hash


@pytest.fixture(autouse=True)
def _leave_cycle2_mode() -> Iterator[None]:
    yield
    cycle2_data.exit_cycle2_mode()


def test_every_band_and_component_has_a_frozen_sd() -> None:
    full = RESULT["full_development_sd"]
    assert set(full) == set(tg.BAND_LABELS)
    for comps in full.values():
        assert set(comps) == set(tg.REPORT_COMPONENTS)
        assert all(v is not None and v >= 0 for v in comps.values())
    assert RESULT["qualifying_days"]["60-120"] == ["Mon", "Tue", "Thu"]


def test_s2_s4_tolerances_are_twice_the_sd_per_component() -> None:
    tol = RESULT["reporting_tolerances_s2_s4"]
    for band, comps in tol.items():
        assert not any(c.startswith("s1_") for c in comps)
        assert len(comps) == 31
        for c, v in comps.items():
            assert v == round(2 * RESULT["full_development_sd"][band][c], 6)


def test_s1_sd_reproduces_the_amendment_2_values() -> None:
    assert all(v["matches"] for v in RESULT["s1_cross_check"].values())


def test_config_holds_the_frozen_rate_range_and_fallbacks() -> None:
    rr = RESULT["rate_range_rps"]
    assert cfg.RATE_RANGE_RPS == (rr["min"], rr["max"]) == (3.2, 82.82805555555555)
    expected = {common.DAYS[d]: list(v) for d, v in cfg.EXPECTED_LODO_FALLBACKS.items()}
    got = {d: v for d, v in RESULT["expected_lodo_fallbacks"].items() if v}
    assert got == expected == {"Mon": ["60-120"], "Tue": ["60-120"], "Thu": ["60-120"]}


def test_result_was_computed_from_the_manifest_caches() -> None:
    manifest = json.loads(cycle2_data.MANIFEST.read_text())["files"]
    assert RESULT["caches"] == manifest
    assert RESULT["wednesday_accessed"] is False
    assert "Wed" not in RESULT["development_days"]


def test_tampered_file_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cfg, "DISPERSION_RESULT_SHA256", "0" * 64)
    with pytest.raises(RuntimeError):
        tg.frozen_dispersion()


@pytest.mark.skipif(
    not (common.CACHE_DIR / "training.npz").exists(), reason="local caches not present (CI)"
)
def test_recomputation_matches_the_frozen_values() -> None:
    cycle2_data.enter_cycle2_mode()
    rows = disp.component_rows(cycle2_data.load_development())
    got = tg.full_development_sd(rows, cycle2_data.DEVELOPMENT_DAYS)
    assert got == RESULT["full_development_sd"]  # deterministic; JSON floats round-trip
    assert tg.rate_range(rows) == cfg.RATE_RANGE_RPS
    assert disp.expected_fallbacks(rows) == RESULT["expected_lodo_fallbacks"]
