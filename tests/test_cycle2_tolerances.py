"""Frozen Cycle 2 S1 band tolerances (Cycle 2 preregistration, Amendment 2)."""

import json
import sys
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "analysis"))
import common  # noqa: E402
import cycle2_config as cfg  # noqa: E402
import cycle2_data  # noqa: E402
import cycle2_tolerances as tol  # noqa: E402

RESULT = json.loads((ROOT / "analysis/results/cycle2/tolerances-s1.json").read_text())


@pytest.fixture(autouse=True)
def _leave_cycle2_mode() -> Iterator[None]:
    yield
    cycle2_data.exit_cycle2_mode()


def test_config_holds_the_computed_tolerances() -> None:
    assert {k: v["tolerance"] for k, v in RESULT["tolerances"].items()} == cfg.S1_TOLERANCES
    assert cfg.S1_TOLERANCES == {"3-10": 0.0924, "10-30": 0.0315, "30-60": 0.0128, "60-120": 0.0065}


def test_every_band_meets_the_support_rule_on_its_own() -> None:
    for band, entry in RESULT["tolerances"].items():
        assert entry["qualifies"], band
        assert len(entry["qualifying_days"]) >= cfg.TOLERANCE_MIN_DAYS
    assert RESULT["tolerances"]["60-120"]["qualifying_days"] == ["Mon", "Tue", "Thu"]
    assert "30-120" not in json.dumps(RESULT["tolerances"])  # merged workaround retired


def test_result_was_computed_from_the_manifest_caches() -> None:
    manifest = json.loads(cycle2_data.MANIFEST.read_text())["files"]
    assert {k: v["sha256"] for k, v in RESULT["caches"].items()} == {
        k: v["sha256"] for k, v in manifest.items()
    }
    assert RESULT["wednesday_accessed"] is False
    assert "Wed" not in RESULT["development_days"]


def test_implementation_reproduces_cycle1_on_training_days() -> None:
    check = RESULT["implementation_check_training_only"]
    assert check["reproduced"] == check["expected_cycle1"]


def test_method_on_synthetic_rows() -> None:
    """2 x max over windows of the ddof=1 SD of per-day sqrt(median CV^2); >= 3 days."""
    days = ("2024-05-10", "2024-05-13", "2024-05-14")
    rows = []
    for i, d in enumerate(days):
        for h in range(3):
            cv2 = np.full(6, (0.1 + 0.01 * i) ** 2)
            rows.append({"day": d, "hour": h, "rate": 70.0, "band": 3, "cv2": cv2})
    out = tol.s1_tolerances(rows, days)["60-120"]
    expected = 2 * np.std([0.10, 0.11, 0.12], ddof=1)
    assert out["qualifies"] and out["tolerance"] == pytest.approx(round(expected, 4))
    two_days = tol.s1_tolerances([r for r in rows if r["day"] != days[2]], days[:2])["60-120"]
    assert not two_days["qualifies"] and two_days.get("tolerance") is None


@pytest.mark.skipif(
    not (common.CACHE_DIR / "training.npz").exists(), reason="local caches not present (CI)"
)
def test_recomputation_matches_the_frozen_values() -> None:
    cycle2_data.enter_cycle2_mode()
    rows = tol.hour_rows(cycle2_data.load_development())
    got = tol.s1_tolerances(rows, cycle2_data.DEVELOPMENT_DAYS)
    assert {k: v["tolerance"] for k, v in got.items()} == cfg.S1_TOLERANCES
