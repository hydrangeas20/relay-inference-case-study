"""The Cycle 2 validation freeze record matches the code, results and caches it pins.

Any change to the frozen validator, the guard, the cache manifest, criterion 3's
source, or the audit code and results fails here. Changing them needs a new dated
amendment and a new freeze record (Cycle 2 preregistration, Amendment 1).
"""

import hashlib
import inspect
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "analysis"))
from relay.traffic import queueing  # noqa: E402

import cycle2_config as cfg  # noqa: E402
import cycle2_validation as v  # noqa: E402

RECORD = json.loads((ROOT / "analysis" / "cycle2_validation_freeze.json").read_text())


def _sha(path: str) -> str:
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


@pytest.mark.parametrize("path", sorted(RECORD["implementation_sha256"]))
def test_frozen_implementation_is_unchanged(path: str) -> None:
    assert _sha(path) == RECORD["implementation_sha256"][path], f"{path} changed after the freeze"


@pytest.mark.parametrize(
    "path", sorted(RECORD["audit"]["code_sha256"]) + sorted(RECORD["audit"]["results_sha256"])
)
def test_audit_code_and_results_are_unchanged(path: str) -> None:
    pinned = {**RECORD["audit"]["code_sha256"], **RECORD["audit"]["results_sha256"]}
    assert _sha(path) == pinned[path]


def test_criterion_3_source_is_unchanged() -> None:
    src = (
        inspect.getsource(queueing.judge)
        + inspect.getsource(queueing.judge_cell)
        + f"NEAR_ZERO={queueing.NEAR_ZERO!r}\n"
    )
    assert (
        hashlib.sha256(src.encode()).hexdigest() == RECORD["rule"]["criterion_3"]["source_sha256"]
    )


def test_record_states_the_rule_the_code_implements() -> None:
    rule = RECORD["rule"]
    assert rule["equivalence_bound_B"] == v.EQUIVALENCE_BOUND == 1.40
    assert rule["safety_rule_C2prime"]["bounds"] == list(v.SAFETY_BOUNDS) == [0.5, 2.0]
    assert rule["nearzero_cap"]["max_fraction"] == v.NEARZERO_CAP == 0.10
    assert rule["folds_required"] == v.FOLDS_REQUIRED == 3
    assert list(rule["gating_folds"].values()) == ["Fri", "Mon", "Tue", "Thu"]
    assert list(rule["gating_folds"]) == list(v.GATING_FOLDS)
    assert rule["criterion_3"]["rule"] == v.CRITERION_3_RULE == "clarified"
    assert "REPORT-ONLY" in rule["azure_vs_azure_bootstrap"]
    assert RECORD["measurement_resolution"] == v.RESOLUTION_STATEMENT


def test_record_pins_the_development_caches_and_the_audit() -> None:
    manifest = json.loads((ROOT / "analysis" / "cycle2_cache_manifest.json").read_text())
    for name, entry in manifest["files"].items():
        assert RECORD["development_caches"]["files"][name]["sha256"] == entry["sha256"]
    assert "2024-05-15" not in json.dumps(RECORD["development_caches"])
    expanded = RECORD["audit"]["expanded"]
    assert expanded["replicates"] == cfg.AUDIT_EXPANDED["replicates"] == 200
    assert expanded["seed_entropy"] == cfg.AUDIT_EXPANDED["seed_entropy"]
    assert RECORD["audit"]["selected"]["B"] == v.EQUIVALENCE_BOUND


def test_record_carries_the_required_statements() -> None:
    s = RECORD["statements"]
    assert "No Cycle 2 candidate" in s["no_candidate_evaluated_before_freeze"]
    assert "remain unopened" in s["wednesday_unopened"]
    assert "can't contain its own SHA" in RECORD["identity_note"]
