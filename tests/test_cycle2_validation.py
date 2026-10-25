"""The frozen Cycle 2 queue-validation rule (Cycle 2 preregistration, Amendment 1).

Synthetic inputs only: no data, no candidate.
"""

import ast
import inspect
import re
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "analysis"))
import common  # noqa: E402
import cycle2_config as cfg  # noqa: E402
import cycle2_data  # noqa: E402
import cycle2_validation as v  # noqa: E402

H, C, K = v.HOURS_PER_FOLD, len(v.CELLS), len(v.METRICS)


@pytest.fixture(autouse=True)
def _leave_cycle2_mode() -> Iterator[None]:
    yield
    cycle2_data.exit_cycle2_mode()


def _fold(model_factor: Any = 1.0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Azure 1.0 everywhere, Poisson far below, model = factor x Azure."""
    azure = np.ones((H, C, K))
    poisson = np.full((H, C, K), 0.3)
    model = azure * model_factor
    return model, poisson, azure


# ---- constants ---------------------------------------------------------------------------


def test_frozen_constants() -> None:
    assert v.EQUIVALENCE_BOUND == 1.40
    assert v.SAFETY_BOUNDS == (0.5, 2.0)
    assert v.NEARZERO_CAP == 0.10
    assert v.FOLDS_REQUIRED == 3
    assert [common.DAYS[d] for d in v.GATING_FOLDS] == ["Fri", "Mon", "Tue", "Thu"]
    assert v.GATING_FOLDS == cfg.GATING_FOLDS
    assert v.CELLS == ((0.2, 0.6), (0.2, 0.8), (1.0, 0.6), (1.0, 0.8))
    assert v.METRICS == ("p95", "p99") and H == 24
    assert v.CRITERION_3_RULE == cfg.CRITERION_3 == "clarified"


# ---- C1': the equivalence interval -------------------------------------------------------


@pytest.mark.parametrize(
    ("ratio", "inside"),
    [(1.40, True), (1.4001, False), (1 / 1.40, True), (0.714, False), (1.0, True), (1.39, True)],
)
def test_equivalence_interval_is_inclusive_one_over_b_to_b(ratio: float, inside: bool) -> None:
    factor = np.ones((C, K))
    factor[3, 1] = ratio  # s 1.0, rho 0.8, p99
    r = v.fold_result(*_fold(factor))
    assert r["C1_prime"] is inside
    assert r["G"]["s1.0_rho0.8_p99"] == pytest.approx(ratio)


def test_g_is_the_geometric_mean_over_informative_hours() -> None:
    model, poisson, azure = _fold()
    model[:12, 0, 0] = 2.0  # half the hours at 2x, half at 1x -> G = sqrt(2)
    model[12, 0, 0] = 0.0  # one-sided near zero: excluded from G
    r = v.fold_result(model, poisson, azure)
    expected = np.exp(np.mean([np.log(2.0)] * 12 + [0.0] * 11))
    assert r["G"]["s0.2_rho0.6_p95"] == pytest.approx(expected)


def test_g_is_one_when_no_hour_is_informative() -> None:
    model, poisson, azure = _fold()
    model[:, 0, 0] = azure[:, 0, 0] = 0.0  # both near zero everywhere: non-informative
    assert v.fold_result(model, poisson, azure)["G"]["s0.2_rho0.6_p95"] == 1.0


# ---- the 3-of-4 rule ---------------------------------------------------------------------


def _results(passing: int, unsafe: tuple[int, ...] = ()) -> dict[str, dict[str, bool]]:
    return {d: {"passed": i < passing, "safety_violation": i in unsafe}
            for i, d in enumerate(v.GATING_FOLDS)}  # fmt: skip


@pytest.mark.parametrize(("passing", "expected"), [(4, True), (3, True), (2, False), (0, False)])
def test_three_of_four_boundary(passing: int, expected: bool) -> None:
    assert v.rule(_results(passing))["passed"] is expected


def test_rule_needs_exactly_the_four_gating_folds() -> None:
    folds = _results(4)
    with pytest.raises(ValueError):
        v.rule({k: folds[k] for k in list(folds)[:3]})
    with pytest.raises(ValueError):
        v.rule({**folds, "2024-05-11": {"passed": True, "safety_violation": False}})


# ---- safety bound C2' --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("ratio", "violation"), [(2.0, False), (2.01, True), (0.5, False), (0.49, True)]
)
def test_safety_bound_is_inclusive_half_to_two(ratio: float, violation: bool) -> None:
    factor = np.ones((C, K))
    factor[1, 0] = ratio
    r = v.fold_result(*_fold(factor))
    assert r["safety_violation"] is violation
    assert r["C1_prime"] is False  # beyond 1.40 anyway


def test_a_safety_violation_fails_the_rule_even_with_four_passing_folds() -> None:
    assert v.rule(_results(4, unsafe=(3,)))["passed"] is False
    assert v.rule(_results(3, unsafe=(3,)))["passed"] is False  # in the failing fold too


# ---- near-zero cap -----------------------------------------------------------------------


@pytest.mark.parametrize(("entries", "ok"), [(19, True), (20, False)])
def test_nearzero_cap_at_ten_percent(entries: int, ok: bool) -> None:
    """19/192 = 9.9% passes, 20/192 = 10.4% fails (24 hours x 4 cells x 2 metrics)."""
    model, poisson, azure = _fold()
    # Fill hour-0 cells metric by metric, so at most 10 of the 96 cells are affected
    # and criterion 3 (>= 80% of cells beat Poisson) still passes.
    order = [(h, c, k) for h in range(H) for c in range(C) for k in range(K)]
    for h, c, k in order[:entries]:
        azure[h, c, k] = 0.0  # one-sided: Azure near zero, model not
    r = v.fold_result(model, poisson, azure)
    assert r["onesided_nearzero_fraction"] == pytest.approx(entries / (H * C * K))
    assert r["nearzero_cap_ok"] is ok
    assert r["criterion_3"]  # the cap, not criterion 3, decides here


# ---- criterion 3 unchanged ---------------------------------------------------------------


def test_criterion_3_is_judge_cell_clarified() -> None:
    from relay.traffic.queueing import judge_cell  # noqa: PLC0415

    rng = np.random.default_rng(11)
    model = rng.lognormal(0, 0.6, (H, C, K))
    poisson = rng.lognormal(-0.5, 0.8, (H, C, K))
    azure = rng.lognormal(0, 0.6, (H, C, K))
    azure[rng.random((H, C, K)) < 0.1] = 0.0
    beats = non_tie = 0
    for h in range(H):
        for i, (s, _rho) in enumerate(v.CELLS):
            d = [dict(zip(v.METRICS, x[h, i], strict=True)) for x in (model, poisson, azure)]
            res = judge_cell(d[0], d[1], d[2], s, "clarified").beats_poisson
            if res is not None:
                non_tie += 1
                beats += res
    r = v.fold_result(model, poisson, azure)
    assert r["criterion_3_beats_fraction"] == pytest.approx(beats / non_tie)
    assert r["criterion_3"] is (beats >= 0.8 * non_tie)


def test_poisson_like_model_fails_criterion_3() -> None:
    model, poisson, azure = _fold()
    assert v.fold_result(poisson.copy(), poisson, azure)["criterion_3"] is False


# ---- equals the audited implementation at B = 1.40 ---------------------------------------


def test_matches_the_audited_vectorised_rule_at_b_1_40() -> None:
    """Every criterion is exercised both ways, and agrees with the audited code each time."""
    import cycle2_operating as op  # noqa: PLC0415

    assert op.EXP["safety_bounds"] == v.SAFETY_BOUNDS
    assert op.EXP["nearzero_cap"] == v.NEARZERO_CAP
    assert v.EQUIVALENCE_BOUND in op.EXP["bounds"]
    rng = np.random.default_rng(3)
    seen: dict[str, set[bool]] = {k: set() for k in ("c1p", "c3", "cap", "safety", "rule")}
    for bias in (1.0, 1.2, 1.5, 2.3, 0.4):
        for noise, onesided in ((0.1, 0.0), (0.4, 0.06), (0.8, 0.14)):
            azure = rng.lognormal(0, 0.5, (1, 4, H, C, K))
            model = azure[0] * bias * rng.lognormal(0, noise, (4, H, C, K))
            poisson = azure[0] * rng.lognormal(np.log(0.35), 0.3, (4, H, C, K))
            azure[rng.random(azure.shape) < onesided] = 0.0
            ev = op.evaluate(model, poisson, azure)
            audited = op.rule_outcomes(ev, v.EQUIVALENCE_BOUND)
            mine = {d: v.fold_result(model[i], poisson[i], azure[0, i])
                    for i, d in enumerate(v.GATING_FOLDS)}  # fmt: skip
            for i, d in enumerate(v.GATING_FOLDS):
                r = mine[d]
                pairs = {
                    "c1p": (r["C1_prime"], audited["c1p"]),
                    "c3": (r["criterion_3"], audited["c3"]),
                    "cap": (r["nearzero_cap_ok"], audited["cap"]),
                    "safety": (r["safety_violation"], audited["safety_fold"]),
                }
                for key, (got, ref) in pairs.items():
                    assert got == bool(ref[0, i]), (key, bias, noise, onesided, d)
                    seen[key].add(got)
                assert mine[d]["passed"] == bool(audited["fold_pass"][0, i])
            assert v.rule(mine)["passed"] == bool(audited["rule"][0])
            seen["rule"].add(v.rule(mine)["passed"])
    assert all(outcomes == {True, False} for outcomes in seen.values()), seen


# ---- what can never gate -----------------------------------------------------------------


def _source() -> str:
    return Path(v.__file__).read_text()


def test_bootstrap_and_azure_vs_azure_cannot_gate() -> None:
    code = _source().split('"""', 2)[2]  # skip the module docstring, which names them
    assert not re.search(r"bootstrap|criterion_audit|azure_vs|\bN2\b", code)
    for fn in (v.rule, v.validate, v.fold_result):
        assert not any("boot" in p or "n2" in p.lower() for p in inspect.signature(fn).parameters)


def test_old_per_cell_criteria_are_not_reachable_from_the_cycle2_path() -> None:
    tree = ast.parse(_source())
    imported = {
        (node.module, alias.name)
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    assert ("relay.traffic.queueing", "judge_cell") in imported
    assert {name for mod, name in imported if mod == "relay.traffic.queueing"} == {
        "NEAR_ZERO",
        "judge_cell",
    }
    code = _source().split('"""', 2)[2]
    forbidden = (
        r"\b(accept|BAND|BOUNDS|_out_of_bounds|criterion_1|criterion_2|CATASTROPHIC\w*"
        r"|fold_verdict|rule_passes|validation_config)\b"
    )
    assert not re.search(forbidden, code)


# ---- the guard ---------------------------------------------------------------------------


def test_validate_runs_inside_the_cache_only_guard() -> None:
    folds = {}
    for d in v.GATING_FOLDS:
        model, poisson, azure = _fold()
        to_cells = lambda x: [[dict(zip(v.METRICS, x[h, c], strict=True)) for c in range(C)]  # noqa: E731
                              for h in range(H)]  # fmt: skip
        folds[d] = {
            "model": to_cells(model),
            "poisson": to_cells(poisson),
            "azure": to_cells(azure),
        }
    out = v.validate(folds)
    assert out["passed"] and out["folds_passing"] == list(v.GATING_FOLDS)
    for phrase in (
        "does not establish",
        "1.15x",
        "71-73%",
        "must not be described as 'matching Azure'",
        "No queue-behavior discrepancy was detected",
    ):
        assert phrase in out["resolution_statement"]
    with pytest.raises(cycle2_data.RawAccessBlocked):
        common.load_split("holdout", allow_holdout=True)
    with pytest.raises(cycle2_data.RawAccessBlocked):
        common.load_split("validation")


def test_config_points_to_the_frozen_rule() -> None:
    assert v.__name__ == cfg.QUEUE_RULE_MODULE
    assert cfg.FOLDS_REQUIRED == v.FOLDS_REQUIRED
