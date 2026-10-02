"""Frozen Cycle 2 settings (docs/validation/phase-2-cycle-2-preregistration.md).

Values here change only by a dated amendment to the Cycle 2 preregistration,
committed before the run it affects.
"""

from __future__ import annotations

# ---- data (section 2) ----------------------------------------------------------------
GATING_FOLDS = ("2024-05-10", "2024-05-13", "2024-05-14", "2024-05-16")  # Fri, Mon, Tue, Thu
REPORTED_FOLDS = ("2024-05-11", "2024-05-12")  # Sat, Sun: reported, not gating
MIN_ELIGIBLE_RATE = 3.0
TOLERANCE_MIN_DAYS = 3  # a band needs >= 3 days with >= 3 eligible hours (Cycle 1 rule)
TOLERANCE_MIN_HOURS_PER_DAY = 3

# ---- queue test (section 6): unchanged from Cycle 1 ----------------------------------
SERVICE_TIMES_S = (0.2, 1.0)
UTILISATIONS = (0.6, 0.8)
SEEDS_PER_CELL = 20
CRITERION_3 = "clarified"  # preregistration (Cycle 1) Amendment 2, A2.3
# Provisional internal pass rule (owner decision Q3), subject to the criterion audit.
FOLDS_REQUIRED = 3  # of the 4 gating folds, each passing all three criteria
CATASTROPHIC_BOUNDS = (0.25, 4.0)  # p95/p99 ratio; no fold may contain a cell beyond these

# ---- criterion audit (section 7) -----------------------------------------------------
AUDIT_SEED_ENTROPY = 20261002
AUDIT_REFERENCE_REPLICATES = 50
AUDIT_TRUTH_PROCESSES = ("cycle1_C1", "bootstrap")
AUDIT_RULE_PASS_MIN = 0.80  # a perfect model must pass the internal rule at least this often
AUDIT_CATASTROPHIC_FALSE_ALARM_MAX = 0.05  # per fold, under the self-consistency null
BOOTSTRAP_MEAN_BLOCK_S = 120

# ---- calibration (section 4) ----------------------------------------------------------
CALIBRATION_SEEDS_PER_HOUR = 3
CALIBRATION_MAX_EVALUATIONS = 300
CALIBRATION_STARTS = 8
SD_FLOOR_FRACTION = 0.25  # sd_days floor: 0.25 x median sd of that statistic across bands

# ---- seed ranges (disjoint by role) ---------------------------------------------------
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
