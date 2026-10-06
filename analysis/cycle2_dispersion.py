"""Cycle 2 Amendment 3 values: full-development dispersion, S2-S4 tolerances, rate range.

Usage: uv run python analysis/cycle2_dispersion.py

Computed from the six development-day caches only (cycle2_data guard), after the
Amendment 3 definitions were committed and before any Candidate D code exists:
  - the full-development across-day SD per band and component (A3.1, A3.5): the
    LODO fallback values and the basis of the reporting tolerances;
  - S2-S4 reporting tolerances, 2 x SD per component, no maxima (A3.1);
  - the observed rate range of eligible hours (A3.8);
  - the expected LODO fallbacks per fold, from the support rule alone (A3.5).
No model is fitted, generated or simulated here.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

import common
import cycle2_config as cfg
import cycle2_data
import cycle2_targets as tg

OUT = Path("analysis/results/cycle2/dispersion-amendment3.json")
S1_RESULT = Path("analysis/results/cycle2/tolerances-s1.json")


def component_rows(days: dict[str, dict[str, np.ndarray]]) -> list[dict[str, Any]]:
    """Eligible hours (as cycle2_tolerances.hour_rows) with their S1-S4 components."""
    rows = []
    for day, arr in days.items():
        for h, th in common.hours(common.dejitter(arr["t"])):
            rate = len(th) / 3600
            band = common.band_of(rate)
            if rate >= cfg.MIN_ELIGIBLE_RATE and band is not None:
                rows.append({"day": day, "hour": h, "rate": rate, "band": band,
                             "stats": tg.hour_components(th)})  # fmt: skip
    return rows


def expected_fallbacks(rows: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Per held-out day: bands whose training days fail the support rule (all components)."""
    out = {}
    for held in cycle2_data.DEVELOPMENT_DAYS:
        training = [d for d in cycle2_data.DEVELOPMENT_DAYS if d != held]
        out[common.DAYS[held]] = [
            label
            for b, label in enumerate(tg.BAND_LABELS)
            if tg.day_dispersion(rows, training, b, "acf_1")[0] is None
        ]
    return out


def main() -> None:
    cycle2_data.enter_cycle2_mode()
    rows = component_rows(cycle2_data.load_development())
    days = cycle2_data.DEVELOPMENT_DAYS
    full_sd = tg.full_development_sd(rows, days)
    qualifying = {
        label: [common.DAYS[d] for d in tg.day_dispersion(rows, days, b, "acf_1")[1]]
        for b, label in enumerate(tg.BAND_LABELS)
    }
    lo, hi = tg.rate_range(rows)
    s1_frozen = json.loads(S1_RESULT.read_text())["tolerances"]
    s1_check = {
        label: {
            "recomputed": {c.removeprefix("s1_"): round(full_sd[label][c], 5) for c in tg.S1},  # type: ignore[arg-type]
            "frozen_sd_by_window": s1_frozen[label]["sd_by_window"],
        }
        for label in tg.BAND_LABELS
    }
    for v in s1_check.values():
        v["matches"] = v["recomputed"] == v["frozen_sd_by_window"]
    record = {
        "computed_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "amendment": "Cycle 2 preregistration, Amendment 3 (A3.1, A3.5, A3.8)",
        "method": "per component: SD (ddof=1) across days with >= 3 eligible band hours of the "
        "day's band-pooled value (S1 sqrt(max(median CV^2, 0)); others the median); band needs "
        ">= 3 such days; tolerance = 2 x SD, no maxima, no floor",
        "development_days": [common.DAYS[d] for d in days],
        "caches": json.loads(cycle2_data.MANIFEST.read_text())["files"],
        "wednesday_accessed": False,
        "eligible_hours": len(rows),
        "qualifying_days": qualifying,
        "full_development_sd": full_sd,
        "reporting_tolerances_s2_s4": {
            band: {c: v for c, v in comps.items() if not c.startswith("s1_")}
            for band, comps in tg.reporting_tolerances(full_sd).items()
        },
        "rate_range_rps": {"min": lo, "max": hi},
        "expected_lodo_fallbacks": expected_fallbacks(rows),
        "s1_cross_check": s1_check,
    }  # fmt: skip
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(record, indent=1) + "\n")
    print(json.dumps({k: record[k] for k in ("qualifying_days", "rate_range_rps",
                                             "expected_lodo_fallbacks")}, indent=1))  # fmt: skip
    print({k: v["matches"] for k, v in s1_check.items()})


if __name__ == "__main__":
    main()
