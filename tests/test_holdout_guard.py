"""The Wednesday holdout can't be read by accident (preregistration §1)."""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "analysis"))
import common  # noqa: E402
import validation_config  # noqa: E402


def test_holdout_raises_without_explicit_permission(tmp_path: Path) -> None:
    with pytest.raises(common.HoldoutAccessError):
        common.load_split("holdout", raw_path=tmp_path / "missing.csv")


def test_splits_are_disjoint_and_cover_the_week() -> None:
    days = [d for s in common.SPLITS.values() for d in s]
    assert len(days) == len(set(days)) == 7
    assert common.HOLDOUT == ("2024-05-15",) and common.DAYS["2024-05-15"] == "Wed"
    assert "2024-05-15" not in common.TRAINING + common.VALIDATION


def test_parser_drops_other_days_before_parsing(tmp_path: Path) -> None:
    csv = tmp_path / "t.csv"
    csv.write_text(
        "TIMESTAMP,ContextTokens,GeneratedTokens\n"
        "2024-05-14 10:00:00.000001+00:00,10,1\n"
        "2024-05-15 10:00:00.000001+00:00,NOT_A_NUMBER,1\n"
        "2024-05-16 10:00:01.500000+00:00,20,2\n"
    )
    out = common._parse(csv, ("2024-05-14", "2024-05-16"))  # the Wednesday row is never parsed
    assert out["2024-05-14"]["ctx"].tolist() == [10]
    assert out["2024-05-16"]["t"].tolist() == [36001.5]


def test_dejitter_stays_within_each_250ms_interval() -> None:
    t = np.sort(np.random.default_rng(0).uniform(0, 100, 10_000))
    d = common.dejitter(t)
    assert np.array_equal(np.sort(np.floor(t / 0.25)), np.floor(d / 0.25))
    assert np.array_equal(common.dejitter(t), d)  # deterministic


def test_validation_refuses_to_run_until_open_items_are_resolved() -> None:
    if validation_config.O1_SIGN_CLAUSE is None or validation_config.O2_HIGH_BAND_TOLERANCE is None:
        with pytest.raises(validation_config.UnresolvedPreregistration):
            validation_config.require_resolved()
