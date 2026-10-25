"""Frozen Cycle 2 settings (docs/validation/phase-2-cycle-2-preregistration.md).

Values here change only by a dated amendment to the Cycle 2 preregistration,
committed before the run it affects.
"""

from __future__ import annotations

import math

# ---- data (section 2) ----------------------------------------------------------------
GATING_FOLDS = ("2024-05-10", "2024-05-13", "2024-05-14", "2024-05-16")  # Fri, Mon, Tue, Thu
REPORTED_FOLDS = ("2024-05-11", "2024-05-12")  # Sat, Sun: reported, not gating
MIN_ELIGIBLE_RATE = 3.0
TOLERANCE_MIN_DAYS = 3  # a band needs >= 3 days with >= 3 eligible hours (Cycle 1 rule)
TOLERANCE_MIN_HOURS_PER_DAY = 3
# FROZEN S1 band tolerances (Cycle 2 preregistration, Amendment 2; computed by
# analysis/cycle2_tolerances.py from the six development days before any candidate).
S1_TOLERANCES = {"3-10": 0.0924, "10-30": 0.0315, "30-60": 0.0128, "60-120": 0.0065}
# FROZEN by Amendment 3 (computed by analysis/cycle2_dispersion.py from the six
# development days, after the A3 definitions were committed and before any D code):
# per band and component, the full-development SD (the LODO fallback, A3.5) and the
# S2-S4 reporting tolerances (2 x SD, A3.1). Read them with
# cycle2_targets.frozen_dispersion(), which verifies this hash.
DISPERSION_RESULT = "analysis/results/cycle2/dispersion-amendment3.json"
DISPERSION_RESULT_SHA256 = "f44bf4bdcd249e93ff89082ca09fefcc320f0ac473d236249333f40731aed851"
# Observed rate range of eligible hours over the six development days (A3.8), rps.
RATE_RANGE_RPS = (3.2, 82.82805555555555)
# Expected LODO fallbacks (A3.5), from the support rule: held-out day -> bands.
EXPECTED_LODO_FALLBACKS = {"2024-05-13": ("60-120",), "2024-05-14": ("60-120",),
                           "2024-05-16": ("60-120",)}  # fmt: skip

# ---- queue test (section 6): unchanged from Cycle 1 ----------------------------------
SERVICE_TIMES_S = (0.2, 1.0)
UTILISATIONS = (0.6, 0.8)
SEEDS_PER_CELL = 20
CRITERION_3 = "clarified"  # preregistration (Cycle 1) Amendment 2, A2.3
# FROZEN queue-validation rule: analysis/cycle2_validation.py (Cycle 2 preregistration,
# Amendment 1). The two values below are the PROVISIONAL rule audited before the freeze;
# they are kept unchanged only because the historical audit code (criterion_audit.py)
# reads them. The Cycle 2 validation path does not use CATASTROPHIC_BOUNDS (retired).
QUEUE_RULE_MODULE = "cycle2_validation"
FOLDS_REQUIRED = 3  # of the 4 gating folds (same value is frozen in cycle2_validation)
CATASTROPHIC_BOUNDS = (0.25, 4.0)  # RETIRED by Amendment 1; historical audit only

# ---- criterion audit (section 7) -----------------------------------------------------
AUDIT_SEED_ENTROPY = 20261002
AUDIT_REFERENCE_REPLICATES = 50
AUDIT_TRUTH_PROCESSES = ("cycle1_C1", "bootstrap")
AUDIT_RULE_PASS_MIN = 0.80  # a perfect model must pass the internal rule at least this often
AUDIT_CATASTROPHIC_FALSE_ALARM_MAX = 0.05  # per fold, under the self-consistency null
BOOTSTRAP_MEAN_BLOCK_S = 120

# Expanded perfect-model audit (owner instruction 2026-10-03; predeclared in
# docs/validation/phase-2-cycle-2-criterion-audit.md section 5 before it runs).
# Fresh seed entropy: its replicates are independent of the original R = 50 audit.
AUDIT_EXPANDED = {
    "replicates": 200,
    "seed_entropy": 20261003,
    "bounds": (1.25, 1.30, 1.35, 1.40),  # the only aggregate equivalence bounds evaluated
    "biases": (1.15, 1.25, 1.30, 1.50),  # multiplicative, applied to the null model's p95/p99
    "safety_bounds": (0.5, 2.0),  # proposed C2': no fold-level G outside these
    "nearzero_cap": 0.10,  # proposed: one-sided near-zero hours <= 10% of a fold's cell-metrics
    "pass_min": 0.80,  # minimum perfect-model 3-of-4 pass probability (unchanged)
    "ci": "Wilson score, 95%",
}

# ---- calibration (section 4) ----------------------------------------------------------
CALIBRATION_SEEDS_PER_HOUR = 3
CALIBRATION_MAX_EVALUATIONS = 300
CALIBRATION_STARTS = 8
SD_FLOOR_FRACTION = 0.25  # sd_days floor: 0.25 x median sd of that statistic across bands

# ---- Candidate D parameter domain and starts (Amendment 3, A3.10 addendum 2) ----------
# FROZEN 2026-10-07: Option W, chosen by the owner before any D code, fit or result.
# Natural units: sigma(lambda) = a * lambda**b, tau in seconds. The optimiser works in
# theta = (log a, b, log tau) (cycle2_optimizer.to_theta).
D_BOUNDS = {"a": (0.05, 5.0), "b": (-1.0, 0.5), "tau_s": (0.1, 600.0)}
D_THETA_LOWER = (math.log(0.05), -1.0, math.log(0.1))
D_THETA_UPPER = (math.log(5.0), 0.5, math.log(600.0))
# Start 8: the Cycle 1 C1 fit (traffic/reference/azure_code_burstiness.json, candidates.C1).
D_CYCLE1_START = {"a": 0.4406544452547643, "b": -0.32313480634892916, "tau_s": 9.23892541130273}
# The eight starts in theta, exactly as cycle2_optimizer.starts(D_THETA_LOWER,
# D_THETA_UPPER, theta(D_CYCLE1_START)) returns them; tests enforce the equality.
D_STARTS_THETA = (
    (-0.6931471805599454, -0.25, 2.04717228111105),  # 1 centre
    (-2.535215254955182, -0.25, 2.04717228111105),  # 2 a low
    (1.148920893835291, -0.25, 2.04717228111105),  # 3 a high
    (-0.6931471805599454, -0.85, 2.04717228111105),  # 4 b low
    (-0.6931471805599454, 0.3500000000000001, 2.04717228111105),  # 5 b high
    (-0.6931471805599454, -0.25, -1.4326336181730261),  # 6 tau low
    (-0.6931471805599454, -0.25, 5.526978180395126),  # 7 tau high
    (-0.8194942815382655, -0.32313480634892916, 2.223425581412457),  # 8 Cycle 1 C1
)

# ---- seed ranges (disjoint by role) ---------------------------------------------------
# Candidate D does not use these ranges: its seeds are hash-derived namespaces
# (analysis/cycle2_seeds.py, Amendment 3, A3.6).
SEED_RANGES = {
    "calibration": (1_000_000, 1_999_999),
    "validation": (2_000_000, 2_999_999),
    "audit": (3_000_000, 3_999_999),
}

# ---- model classes and variant cap (section 3) ----------------------------------------
VARIANTS = {
    "D": ("D1",),  # salvage: one-timescale lognormal OU, higher-order targets
    "A": ("A1", "A2"),  # two-timescale + sinh-arcsinh link; A1 constant xi, A2 xi(lambda)
    "B": ("B2", "B3"),  # MMPP with K = 2 and K = 3 states
}
EFFECTIVE_PARAMETERS = {"D1": 3, "A1": 6, "A2": 7, "B2": 5, "B3": 8}
WEDNESDAY_ELIGIBLE = ("D1", "A1", "A2", "B2", "B3")  # comparator C is never eligible
