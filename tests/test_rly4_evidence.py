"""The RLY-4 evidence, the report generator and the independent recomputation must agree.

Added in the PR #3 review. analyze.py (the report) and review/recompute.py (written
separately, sharing no code) both read the committed records in results/rly-4. If either
drifts, or a committed record changes, these tests fail. The headline figures quoted in
the README and the ticket write-up are pinned here too.
"""

from __future__ import annotations

import importlib.util
import json
import statistics
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results" / "rly-4"
TICKET = ROOT / "tickets" / "rly-4-prefix-caching"

pytestmark = pytest.mark.skipif(not RESULTS.is_dir(), reason="RLY-4 results not present")


def _module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def recompute() -> ModuleType:
    return _module(TICKET / "review" / "recompute.py", "rly4_recompute")


@pytest.fixture(scope="module")
def runs(recompute: ModuleType) -> dict[str, list[dict[str, Any]]]:
    return {c: recompute.load(RESULTS, c) for c in recompute.CONFIGS}


@pytest.fixture(scope="module")
def report() -> dict[str, Any]:
    return json.loads((RESULTS / "report.json").read_text())  # type: ignore[no-any-return]


def test_validity_recomputed_from_raw_send_times_matches_summaries(
    runs: dict[str, list[dict[str, Any]]],
) -> None:
    flat = [r for rs in runs.values() for r in rs]
    assert len(flat) == 17
    assert all(r["valid"] == r["summary_valid"] for r in flat)
    assert sum(not r["valid"] for r in flat) == 4


def test_two_cache_telemetry_sources_agree(runs: dict[str, list[dict[str, Any]]]) -> None:
    for rs in runs.values():
        for r in rs:
            assert r["metrics_cached"] == pytest.approx(sum(r["cache_n"].values()))
            assert r["metrics_evaluated"] == pytest.approx(sum(r["prompt_n"].values()))


def test_report_matches_independent_recomputation(
    runs: dict[str, list[dict[str, Any]]], report: dict[str, Any]
) -> None:
    for cfg, rs in runs.items():
        valid = [r for r in rs if r["valid"]]
        agg = report["configs"][cfg]["aggregate"]
        assert agg["valid_runs"] == len(valid)
        assert agg["ttft_p50_s"]["median"] == pytest.approx(
            statistics.median(r["p50"] for r in valid)
        )
        assert agg["ttft_p95_s"]["median"] == pytest.approx(
            statistics.median(r["p95"] for r in valid)
        )
        assert agg["cached_fraction"]["median"] == pytest.approx(
            statistics.median(r["share_metrics"] for r in valid)
        )


def test_headline_figures(recompute: ModuleType, runs: dict[str, list[dict[str, Any]]]) -> None:
    orig = [r for r in runs["shared-original-cache"] if r["valid"]]
    fix = [r for r in runs["shared-metadata-cache"] if r["valid"]]
    share_o = statistics.median(r["share_metrics"] for r in orig)
    share_f = statistics.median(r["share_metrics"] for r in fix)
    p50_o = statistics.median(r["p50"] for r in orig)
    p50_f = statistics.median(r["p50"] for r in fix)
    assert round(share_o * 100, 1) == 0.5
    assert round(share_f * 100, 1) == 82.9
    assert round(p50_o * 1000) == 2524 and round(p50_f * 1000) == 654
    # "3.9x" in the README is the ratio of median per-run p50s, not a paired figure.
    assert round(p50_o / p50_f, 1) == 3.9
    paired = recompute.paired(orig, fix)
    assert round(paired["median_ratio"], 2) == 0.22
