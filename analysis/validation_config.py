"""Frozen settings for the preregistered validation (docs/validation/phase-2-preregistration.md).

Values here must match the preregistration. They change only by a dated amendment to
the preregistration, committed before the run it affects.
"""

from __future__ import annotations

# §10 open items, resolved by preregistration Amendment 1 (2026-09-28).
# A1.1: the sign clause is a reported diagnostic, not a pass/fail clause.
O1_SIGN_CLAUSE: str | None = "diagnostic"  # "pass/fail" | "dropped" | "diagnostic"
# "a-merged": one pooled 30-120 band checked at 0.0102; "a-separate": 30-60 and 60-120
# checked separately, both at 0.0102; "b": 60-120 at 0.0035; "c": 60-120 at 0.0146.
# A1.2: 0.0102 from the merged 30-120 training population; 30-60 and 60-120 evaluated
# separately, both at 0.0102 (supersedes 0.0146 for 30-60, including band holdouts).
O2_HIGH_BAND_TOLERANCE: str | None = "a-separate"

# §6.1 tolerances (training days only), keyed by fit band.
TOLERANCES: dict[str, float] = {"3-10": 0.0985, "10-30": 0.0321, "30-60": 0.0146}
O2_OPTIONS: dict[str, float] = {"a-merged": 0.0102, "a-separate": 0.0102, "b": 0.0035, "c": 0.0146}

# §6.3 holdout roles, by fit-band index.
INTERPOLATION_HOLDOUTS = (1, 2)  # 10-30, 30-60: count toward generalization
EXTRAPOLATION_HOLDOUTS = (0, 3)  # 3-10, 60-120: reported only

# §7 queueing test.
SERVICE_TIMES_S = (0.2, 1.0)
UTILISATIONS = (0.6, 0.8)
SEEDS = tuple(range(1, 21))
MODEL_SEED_BASE = 10_000
POISSON_SEED_OFFSET = 500_000

# §8 prompt fidelity.
FIDELITY_TRACE = {"start": "15:00", "minutes": 60, "peak_rps": 8.0, "seed": 20260928}

# §9 sensitivity.
SENSITIVITY_DAY_TRACE = {"peak_rps": 20.0, "seed": 20260928}


class UnresolvedPreregistration(RuntimeError):
    pass


def require_resolved() -> None:
    if O1_SIGN_CLAUSE is None or O2_HIGH_BAND_TOLERANCE is None:
        raise UnresolvedPreregistration(
            "preregistration open items O1/O2 are unresolved; candidate validation can't run "
            "until they are resolved by a dated amendment (preregistration §10)"
        )


def check_bands() -> list[tuple[str, tuple[float, float], float]]:
    """(label, rate range, tolerance) for each Thursday/holdout band check."""
    require_resolved()
    o2 = str(O2_HIGH_BAND_TOLERANCE)
    bands = [
        ("3-10", (3.0, 10.0), TOLERANCES["3-10"]),
        ("10-30", (10.0, 30.0), TOLERANCES["10-30"]),
    ]
    if o2 == "a-merged":
        bands.append(("30-120", (30.0, 120.0), O2_OPTIONS[o2]))
    elif o2 == "a-separate":
        bands += [
            ("30-60", (30.0, 60.0), O2_OPTIONS[o2]),
            ("60-120", (60.0, 120.0), O2_OPTIONS[o2]),
        ]
    else:
        bands += [
            ("30-60", (30.0, 60.0), TOLERANCES["30-60"]),
            ("60-120", (60.0, 120.0), O2_OPTIONS[o2]),
        ]
    return bands
