"""Seed derivation for Cycle 2 candidate work (Cycle 2 preregistration, Amendment 3, A3.6)."""

import hashlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "analysis"))
import cycle2_data  # noqa: E402
import cycle2_seeds as seeds  # noqa: E402

FITS = ("all", *cycle2_data.DEVELOPMENT_DAYS,
        *(f"without-band-{b}" for b in ("3-10", "10-30", "30-60", "60-120")))  # fmt: skip


def test_derivation_is_the_documented_hash() -> None:
    key = b"relay/cycle2/D/calibration/v1|all|2024-05-10|7|2"
    expected = int.from_bytes(hashlib.sha256(key).digest()[:8], "big")
    assert seeds.calibration_seed("all", "2024-05-10", 7, 2) == expected
    assert seeds.derive_seed("ns", 1, "x") == int.from_bytes(
        hashlib.sha256(b"ns|1|x").digest()[:8], "big"
    )


def test_recorded_reference_values() -> None:
    """Pinned so that any change to the derivation is caught."""
    assert seeds.NAMESPACES == {
        "D_calibration": "relay/cycle2/D/calibration/v1",
        "D_validation": "relay/cycle2/D/validation/v1",
        "poisson_validation": "relay/cycle2/poisson-control/validation/v1",
    }
    ref = seeds.validation_seed("poisson", "2024-05-13", 0, 0, 0)
    assert ref == int.from_bytes(
        hashlib.sha256(b"relay/cycle2/poisson-control/validation/v1|2024-05-13|0|0|0").digest()[:8],
        "big",
    )


def test_deterministic_and_generator_reproducible() -> None:
    a = seeds.rng(seeds.NAMESPACES["D_validation"], "2024-05-14", 3, 1, 5).random(4)
    b = seeds.rng(seeds.NAMESPACES["D_validation"], "2024-05-14", 3, 1, 5).random(4)
    assert (a == b).all()


def test_streams_differ_for_identical_indices() -> None:
    d = seeds.validation_seed("D", "2024-05-10", 4, 2, 3)
    p = seeds.validation_seed("poisson", "2024-05-10", 4, 2, 3)
    c = seeds.derive_seed(seeds.NAMESPACES["D_calibration"], "2024-05-10", 4, 2, 3)
    assert len({d, p, c}) == 3


def test_no_planned_seed_collides_within_or_across_streams() -> None:
    planned = list(seeds.planned_seeds(cycle2_data.DEVELOPMENT_DAYS, FITS))
    n_cal = len(FITS) * 6 * 24 * 3
    n_val = 6 * 24 * 4 * 20
    tags = [t for t, _ in planned]
    assert tags.count("D_calibration") == n_cal
    assert tags.count("D_validation") == tags.count("poisson_validation") == n_val
    values = [s for _, s in planned]
    assert len(set(values)) == len(values)
    assert all(0 <= s < 2**64 for s in values)


def test_counts_are_the_preregistered_ones() -> None:
    assert seeds.CALIBRATION_REPLICATES == 3
    assert seeds.VALIDATION_REPLICATES == 20
    assert seeds.CELLS == 4


@pytest.mark.parametrize(
    "args",
    [("D", "d", 0, 4, 0), ("D", "d", 0, 0, 20), ("poisson", "d", 0, -1, 0), ("A", "d", 0, 0, 0)],
)
def test_validation_seed_rejects_out_of_range(args: tuple) -> None:  # type: ignore[type-arg]
    with pytest.raises(ValueError):
        seeds.validation_seed(*args)


def test_calibration_seed_rejects_out_of_range() -> None:
    with pytest.raises(ValueError):
        seeds.calibration_seed("all", "2024-05-10", 0, 3)
