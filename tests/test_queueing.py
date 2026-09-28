import math

import numpy as np
import pytest

from relay.traffic.queueing import (
    CellVerdict,
    accept,
    fifo_start_times,
    judge,
    judge_cell,
    queue_metrics,
    servers_for,
)


def test_simultaneous_arrivals() -> None:
    a = np.zeros(3)
    assert fifo_start_times(a, 1, 1.0).tolist() == [0.0, 1.0, 2.0]
    assert fifo_start_times(a, 2, 1.0).tolist() == [0.0, 0.0, 1.0]
    m = queue_metrics(a, 1, 1.0, 10.0)
    assert m.fraction_waiting == pytest.approx(2 / 3)
    assert m.peak_waiting == 2


def test_md1_mean_wait_matches_theory() -> None:
    rng = np.random.default_rng(0)
    lam, s = 10.0, 0.07
    a = np.cumsum(rng.exponential(1 / lam, 300_000))
    wait = fifo_start_times(a, 1, s) - a
    rho = lam * s
    assert wait.mean() == pytest.approx(rho * s / (2 * (1 - rho)), rel=0.05)


def test_no_waiting_below_capacity_when_spaced() -> None:
    a = np.arange(0, 100, 1.0)
    m = queue_metrics(a, 1, 0.5, 100.0)
    assert m.p99 == 0.0 and m.fraction_waiting == 0.0


def test_servers_for() -> None:
    assert servers_for(80.0, 1.0, 0.6) == math.ceil(80 / 0.6)
    assert servers_for(0.1, 0.2, 0.8) == 1


def test_near_zero_rule() -> None:
    s = 1.0
    assert judge(0.001, 0.002, s).agrees_near_zero
    assert judge(0.001, 0.5, s).fails_near_zero
    assert judge(0.5, 0.001, s).fails_near_zero
    v = judge(1.2, 1.0, s)
    assert v.ratio == pytest.approx(1.2) and v.log_error == pytest.approx(math.log(1.2))


def test_cell_verdicts() -> None:
    s = 1.0
    az = {"p95": 1.0, "p99": 2.0}
    good = judge_cell({"p95": 1.2, "p99": 2.5}, {"p95": 0.3, "p99": 0.4}, az, s)
    assert good.in_band and not good.out_of_bounds and good.beats_poisson
    bad = judge_cell({"p95": 3.0, "p99": 2.0}, {"p95": 1.0, "p99": 2.0}, az, s)
    assert not bad.in_band and bad.out_of_bounds and bad.beats_poisson is False
    zero = {"p95": 0.0, "p99": 0.0}
    tie = judge_cell(zero, zero, zero, s)
    assert tie.in_band and tie.beats_poisson is None
    one_sided = judge_cell({"p95": 0.5, "p99": 0.5}, zero, zero, s)
    assert not one_sided.in_band and one_sided.out_of_bounds


def test_acceptance_thresholds() -> None:
    passing = [CellVerdict(True, False, True)] * 8 + [CellVerdict(False, False, True)] * 2
    assert accept(passing).passed
    too_few = [CellVerdict(True, False, True)] * 7 + [CellVerdict(False, False, True)] * 3
    assert not accept(too_few).criterion_1
    oob = [CellVerdict(True, False, True)] * 9 + [CellVerdict(True, True, True)]
    assert not accept(oob).criterion_2
    ties = (
        [CellVerdict(True, False, None)] * 5
        + [CellVerdict(True, False, True)] * 4
        + [CellVerdict(True, False, False)]
    )
    result = accept(ties)
    assert result.ties == 5 and result.non_tie == 5 and result.criterion_3
