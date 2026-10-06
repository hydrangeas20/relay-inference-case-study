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


def test_vectorised_criterion_3_and_g_match_the_frozen_functions() -> None:
    """cycle2_operating.evaluate must equal queueing.judge_cell (clarified) and the G definition."""
    from relay.traffic.queueing import judge_cell  # noqa: PLC0415

    import cycle2_operating as op  # noqa: PLC0415

    rng = np.random.default_rng(7)
    shape = (2, 6, len(op.CELLS), 2)  # folds, hours, cells, metrics

    def draw(size: tuple[int, ...]) -> np.ndarray:
        x = rng.lognormal(-1.0, 1.0, size)
        return np.where(rng.random(size) < 0.2, rng.uniform(0, 0.003, size), x)  # some near zero

    model, poisson, ref = draw(shape), draw(shape), draw((3, *shape))
    ev = op.evaluate(model, poisson, ref)
    for r in range(3):
        for f in range(2):
            verdicts, logs = [], {}
            for h in range(6):
                for i, (s, _rho) in enumerate(op.CELLS):
                    m = dict(zip(op.METRICS, model[f, h, i], strict=True))
                    p = dict(zip(op.METRICS, poisson[f, h, i], strict=True))
                    a = dict(zip(op.METRICS, ref[r, f, h, i], strict=True))
                    verdicts.append(judge_cell(m, p, a, s, "clarified").beats_poisson)
                    for j, k in enumerate(op.METRICS):
                        if m[k] >= 0.01 * s and a[k] >= 0.01 * s:
                            logs.setdefault((i, j), []).append(np.log(m[k] / a[k]))
            non_tie = [v for v in verdicts if v is not None]
            expected_c3 = bool(non_tie) and sum(non_tie) >= 0.8 * len(non_tie)
            assert bool(ev["criterion_3"][r, f]) == expected_c3
            assert ev["beats_fraction"][r, f] == pytest.approx(sum(non_tie) / max(1, len(non_tie)))
            for (i, j), v in logs.items():
                assert ev["log_g"][r, f, i, j] == pytest.approx(np.mean(v))


def test_rule_outcomes_and_wilson() -> None:
    import cycle2_operating as op  # noqa: PLC0415

    lo, hi = op.wilson(160, 200)
    assert lo < 0.8 < hi and hi - lo < 0.12
    log_g = np.zeros((1, 4, len(op.CELLS), 2))
    log_g[0, 0, 0, 0] = np.log(1.3)  # fold 0 outside 1.25, inside 1.35
    ev = {
        "log_g": log_g,
        "max_abs_log_g": np.abs(log_g).max(axis=(2, 3)),
        "onesided_fraction": np.zeros((1, 4)),
        "criterion_3": np.ones((1, 4), dtype=bool),
    }
    assert op.rule_outcomes(ev, 1.25)["fold_pass"].sum() == 3
    assert op.rule_outcomes(ev, 1.25)["rule"][0]  # 3 of 4 still passes
    ev["log_g"][0, 1, 0, 0] = np.log(2.5)  # a safety violation in another fold
    ev["max_abs_log_g"] = np.abs(ev["log_g"]).max(axis=(2, 3))
    assert not op.rule_outcomes(ev, 1.35)["rule"][0]
