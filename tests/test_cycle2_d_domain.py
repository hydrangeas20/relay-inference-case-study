"""Frozen Candidate D domain, starts and procedure (Cycle 2 preregistration, Amendment 3).

Option W was frozen on 2026-10-07 before any Candidate D code, fit or result. Any change
to the bounds, the starts, or the pinned procedure modules fails here and needs a new
dated amendment committed before the run it affects.
"""

import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "analysis"))
import cycle2_config as cfg  # noqa: E402
import cycle2_optimizer as opt  # noqa: E402
import cycle2_seeds as seeds  # noqa: E402

# The D procedure frozen by Amendment 3: definitions 8217fde; code 03db1d6;
# targets loader 6a7602a.
PROCEDURE_SHA256 = {
    "analysis/cycle2_optimizer.py": (
        "11fc05677988503a4e899285134da0206b35f8ab1f73fb2ccd301074bb2f3921"
    ),
    "analysis/cycle2_seeds.py": (
        "058a72ca05c29ffbbcc2a25c4d91e3e75051b20f4a1170cf2aff6faf050ca042"
    ),
    "analysis/cycle2_targets.py": (
        "f0837126afee47b977df64ee6da276f7c5803dee179d548edcece801b4d22e8a"
    ),
}
# Earlier freezes this one must leave untouched.
PRIOR_SHA256 = {
    "analysis/cycle2_validation_freeze.json": (  # Amendment 1 freeze record
        "2bda4bf273d57dd487d38e8ff9231ef7a3e9f07f90fb2e26e52f8b58771cab30"
    ),
    "analysis/results/cycle2/tolerances-s1.json": (  # Amendment 2 S1 tolerances
        "1a2fb0428fdb6224e94b1afff470a9f7f0d9bfd43c77f1aad365e57c79463f72"
    ),
}


def _sha(path: str) -> str:
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


@pytest.mark.parametrize("path", sorted(PROCEDURE_SHA256))
def test_procedure_modules_are_unchanged(path: str) -> None:
    assert _sha(path) == PROCEDURE_SHA256[path], f"{path} changed after the D freeze"


def test_prior_freeze_record_is_unchanged() -> None:
    for path, digest in PRIOR_SHA256.items():
        assert _sha(path) == digest, f"{path} changed"
    assert _sha(cfg.DISPERSION_RESULT) == cfg.DISPERSION_RESULT_SHA256


def test_bounds_are_option_w() -> None:
    assert cfg.D_BOUNDS == {"a": (0.05, 5.0), "b": (-1.0, 0.5), "tau_s": (0.1, 600.0)}
    lo, hi = zip(*(cfg.D_BOUNDS[k] for k in ("a", "b", "tau_s")), strict=True)
    assert (math.log(lo[0]), lo[1], math.log(lo[2])) == cfg.D_THETA_LOWER
    assert (math.log(hi[0]), hi[1], math.log(hi[2])) == cfg.D_THETA_UPPER


def test_start_8_is_the_recorded_cycle1_fit() -> None:
    ref = json.loads((ROOT / "traffic/reference/azure_code_burstiness.json").read_text())
    c1 = ref["candidates"]["C1"]
    assert set(c1["band_taus"]) == {cfg.D_CYCLE1_START["tau_s"]}
    assert (c1["a"], c1["b"]) == (cfg.D_CYCLE1_START["a"], cfg.D_CYCLE1_START["b"])


def test_frozen_starts_equal_the_design_mapped_onto_option_w() -> None:
    c1 = opt.to_theta(*(cfg.D_CYCLE1_START[k] for k in ("a", "b", "tau_s")))
    got = opt.starts(np.array(cfg.D_THETA_LOWER), np.array(cfg.D_THETA_UPPER), c1)
    assert len(cfg.D_STARTS_THETA) == 8
    assert [tuple(float(x) for x in s) for s in got] == list(cfg.D_STARTS_THETA)


def test_starts_in_natural_units_match_the_amendment_table() -> None:
    table = [(0.5, -0.25, 7.746), (0.07924, -0.25, 7.746), (3.155, -0.25, 7.746),
             (0.5, -0.85, 7.746), (0.5, 0.35, 7.746), (0.5, -0.25, 0.2387),
             (0.5, -0.25, 251.4), (0.44065, -0.32314, 9.2389)]  # fmt: skip
    for theta, row in zip(cfg.D_STARTS_THETA, table, strict=True):
        p = opt.from_theta(theta)
        assert (p["a"], p["b"], p["tau_s"]) == pytest.approx(row, rel=1e-3, abs=1e-9)


def test_procedure_settings_unchanged() -> None:
    assert opt.BUDGET == cfg.CALIBRATION_MAX_EVALUATIONS == 300
    assert opt.STARTS == cfg.CALIBRATION_STARTS == 8
    assert (opt.REFLECT, opt.EXPAND, opt.CONTRACT, opt.SHRINK) == (1.0, 2.0, 0.5, 0.5)
    assert opt.SIMPLEX_STEP_FRACTION == 0.10 and opt.FTOL == opt.XTOL == 1e-4
    assert seeds.CALIBRATION_REPLICATES == cfg.CALIBRATION_SEEDS_PER_HOUR == 3
    assert seeds.VALIDATION_REPLICATES == cfg.SEEDS_PER_CELL == 20
    assert cfg.RATE_RANGE_RPS == (3.2, 82.82805555555555)
