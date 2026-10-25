"""Cycle 2 S1 band tolerances (Cycle 2 preregistration, section 5).

Usage: uv run python analysis/cycle2_tolerances.py

Method (section 5 = Cycle 1 §6.1, as implemented in analysis/azure_traffic.py
`tolerances`): for each rate band, take each development day with >= 3 eligible hours
in the band; that day's pooled curve is sqrt(max(element-wise median of CV^2(W) over
the day's band hours, 0)) for W in {1, 2, 5, 10, 30, 60} s; the band's tolerance is
2 x the maximum over windows of the across-day standard deviation (ddof = 1). A band
qualifies only with >= 3 such days (Cycle 2 support rule).

Only S1 is computed here. S2-S4 tolerances are NOT computed: section 5 doesn't
determine them uniquely (see Cycle 2 preregistration, Amendment 2).

Cache-only (cycle2_data). As a check of the implementation, the same function on the
five training days alone reproduces Cycle 1's recorded tolerances.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from relay.traffic.stats import WINDOWS_S, rate_cv2

import common
import cycle2_config as cfg
import cycle2_data

OUT = Path("analysis/results/cycle2/tolerances-s1.json")
TRAINING = ("2024-05-10", "2024-05-11", "2024-05-12", "2024-05-13", "2024-05-14")


def hour_rows(days: dict[str, dict[str, np.ndarray]]) -> list[dict[str, Any]]:
    rows = []
    for day, arr in days.items():
        for h, th in common.hours(common.dejitter(arr["t"])):
            rate = len(th) / 3600
            band = common.band_of(rate)
            if rate >= cfg.MIN_ELIGIBLE_RATE and band is not None:
                rows.append({"day": day, "hour": h, "rate": rate, "band": band,
                             "cv2": rate_cv2(th, 3600)})  # fmt: skip
    return rows


def s1_tolerances(rows: list[dict[str, Any]], day_order: tuple[str, ...]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for b, (lo, hi) in enumerate(common.RATE_BANDS):
        label = f"{lo:g}-{hi:g}"
        hours_by_day = {d: [r for r in rows if r["day"] == d and r["band"] == b] for d in day_order}
        qualifying = [
            d for d in day_order if len(hours_by_day[d]) >= cfg.TOLERANCE_MIN_HOURS_PER_DAY
        ]
        entry: dict[str, Any] = {
            "eligible_hours_by_day": {common.DAYS[d]: len(hours_by_day[d]) for d in day_order},
            "qualifying_days": [common.DAYS[d] for d in qualifying],
            "qualifies": len(qualifying) >= cfg.TOLERANCE_MIN_DAYS,
        }
        if len(qualifying) >= 2:
            daily = np.array([
                np.sqrt(np.clip(np.median([r["cv2"] for r in hours_by_day[d]], axis=0), 0, None))
                for d in qualifying
            ])  # fmt: skip
            sd = np.std(daily, axis=0, ddof=1)
            entry["sd_by_window"] = dict(
                zip([str(w) for w in WINDOWS_S], sd.round(5).tolist(), strict=True)
            )
            entry["tolerance"] = round(2 * float(sd.max()), 4) if entry["qualifies"] else None
        out[label] = entry
    return out


def main() -> None:
    cycle2_data.enter_cycle2_mode()
    days = cycle2_data.load_development()
    rows = hour_rows(days)
    development = s1_tolerances(rows, cycle2_data.DEVELOPMENT_DAYS)
    check = s1_tolerances([r for r in rows if r["day"] in TRAINING], TRAINING)
    record = {
        "computed_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "statistic": "S1 = sqrt(max(CV^2(W), 0)), W in {1, 2, 5, 10, 30, 60} s",
        "method": "Cycle 2 preregistration section 5 = Cycle 1 §6.1 (azure_traffic.tolerances): "
        "2 x max over windows of the across-day SD (ddof=1) of daily pooled curves; days with "
        ">= 3 eligible hours in the band; band qualifies with >= 3 such days",
        "development_days": [common.DAYS[d] for d in cycle2_data.DEVELOPMENT_DAYS],
        "caches": json.loads(cycle2_data.MANIFEST.read_text())["files"],
        "wednesday_accessed": False,
        "tolerances": development,
        "implementation_check_training_only": {
            "expected_cycle1": {"3-10": 0.0985, "10-30": 0.0321, "30-60": 0.0146, "60-120": 0.0035},
            "reproduced": {k: (v.get("tolerance") if v["qualifies"] else
                               round(2 * max(v["sd_by_window"].values()), 4) if "sd_by_window" in v else None)
                           for k, v in check.items()},
        },
    }  # fmt: skip
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(record, indent=1) + "\n")
    print(json.dumps(record["tolerances"], indent=1))
    print(json.dumps(record["implementation_check_training_only"], indent=1))


if __name__ == "__main__":
    main()
