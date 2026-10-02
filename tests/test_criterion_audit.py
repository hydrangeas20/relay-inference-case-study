"""The criterion audit's building blocks, on synthetic inputs only (no data)."""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "analysis"))
import criterion_audit as audit  # noqa: E402
import cycle2_config as cfg  # noqa: E402


def _pool(rate: float, n: int = 3) -> list[tuple[np.ndarray, np.ndarray]]:
    rng = np.random.default_rng(0)
    return [(rng.poisson(rate, 3600), np.full(3600, rate)) for _ in range(n)]


def test_bootstrap_thins_to_the_target_trend() -> None:
    counts, superposed = audit.bootstrap_counts(
        np.full(3600, 10.0), _pool(20.0), np.random.default_rng(1)
    )
    assert counts.mean() == pytest.approx(10.0, rel=0.03)
    assert superposed == 0.0


def test_bootstrap_superposes_when_the_target_is_higher() -> None:
    counts, superposed = audit.bootstrap_counts(
        np.full(3600, 30.0), _pool(20.0), np.random.default_rng(2)
    )
    assert counts.mean() == pytest.approx(30.0, rel=0.03)
    assert superposed == 1.0


def test_bootstrap_is_deterministic_for_a_seed() -> None:
    a, _ = audit.bootstrap_counts(np.full(3600, 10.0), _pool(20.0), np.random.default_rng(5))
    b, _ = audit.bootstrap_counts(np.full(3600, 10.0), _pool(20.0), np.random.default_rng(5))
    assert np.array_equal(a, b)


def test_bootstrap_keeps_source_modulation() -> None:
    # A source whose rate alternates in 60 s blocks between 10 and 30 rps.
    level = np.repeat(np.tile([10.0, 30.0], 30), 60)
    rng = np.random.default_rng(3)
    pool = [(rng.poisson(level), np.full(3600, 20.0))]
    counts, _ = audit.bootstrap_counts(np.full(3600, 20.0), pool, np.random.default_rng(4))
    assert counts.var() / counts.mean() > 3  # far above Poisson's 1


@pytest.mark.parametrize(
    ("model", "ref", "s", "expected"),
    [
        ({"p95": 1.0, "p99": 5.0}, {"p95": 1.0, "p99": 1.0}, 1.0, True),  # ratio 5 > 4
        ({"p95": 1.0, "p99": 3.0}, {"p95": 1.0, "p99": 1.0}, 1.0, False),  # within 0.25-4
        ({"p95": 1.0, "p99": 0.2}, {"p95": 1.0, "p99": 1.0}, 1.0, True),  # ratio 0.2 < 0.25
        ({"p95": 0.0, "p99": 0.001}, {"p95": 0.0, "p99": 0.0}, 1.0, False),  # both near zero
        ({"p95": 0.0, "p99": 0.5}, {"p95": 0.0, "p99": 0.0}, 1.0, True),  # one-sided at A = 0
    ],
)
def test_catastrophic_cell(model: dict, ref: dict, s: float, expected: bool) -> None:
    assert audit.catastrophic_cell(model, ref, s) is expected


def _fold(passed: bool, catastrophic: int = 0) -> dict:
    return {"passed": passed, "catastrophic_cells": catastrophic}


def test_rule_needs_three_of_four_and_no_catastrophe() -> None:
    assert cfg.FOLDS_REQUIRED == 3
    assert audit.rule_passes([_fold(True)] * 4)
    assert audit.rule_passes([_fold(True)] * 3 + [_fold(False)])
    assert not audit.rule_passes([_fold(True)] * 2 + [_fold(False)] * 2)
    assert not audit.rule_passes([_fold(True)] * 3 + [_fold(False, catastrophic=1)])
    assert not audit.rule_passes([_fold(True, catastrophic=1)] + [_fold(True)] * 3)


def test_a_perfect_fold_passes_and_poisson_like_model_fails() -> None:
    cells = len(audit.CELLS) * 6
    ref = [{"p95": 1.0, "p99": 2.0}] * cells
    poisson = [{"p95": 0.3, "p99": 0.5}] * cells
    good = audit.fold_verdict(ref, poisson, ref)
    assert good["passed"] and good["catastrophic_cells"] == 0
    bad = audit.fold_verdict(poisson, poisson, ref)
    assert not bad["passed"]
