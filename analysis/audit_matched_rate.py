"""Matched-rate comparison: an Azure hour vs the model driven by that hour's own trend.

Usage: uv run python analysis/audit_matched_rate.py --day Tue --hour 18 [--candidate C1]

For one training hour, compares Azure's de-jittered arrivals, the candidate model with
expected rate equal to the hour's 10-minute trend, and random (Poisson) arrivals on the
same trend: rate fluctuation at 1-60 s, 1 s autocorrelation, and queue waits (8 servers,
85% utilisation, the cell inspected in the 2026-09-28 audit). Descriptive only; the
preregistered queueing test is analysis/validate.py. Training days only.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from relay.traffic.burstiness import BurstinessModel, load_candidate
from relay.traffic.generate import BIN_S, cox_arrivals
from relay.traffic.queueing import queue_metrics
from relay.traffic.stats import moving_average_trend, per_second_counts, rate_cv2

import common


def describe(t: np.ndarray, rate: float) -> dict[str, object]:
    per_s = per_second_counts(t, 3600)
    x = per_s - moving_average_trend(per_s)
    acf = [float(np.corrcoef(x[:-lag], x[lag:])[0, 1]) for lag in (1, 5, 10, 30)]
    s = 0.85 * 8 / rate
    q = queue_metrics(t, 8, s, 3600.0)
    return {"rate_cv": np.sqrt(np.clip(rate_cv2(t, 3600), 0, None)).round(4).tolist(),
            "acf_1_5_10_30": np.round(acf, 3).tolist(),
            "wait_p50_p99_in_service_times": [q.p50 / s, q.p99 / s]}  # fmt: skip


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--day", choices=[common.DAYS[d] for d in common.TRAINING], required=True)
    parser.add_argument("--hour", type=int, required=True)
    parser.add_argument("--candidate", choices=("C1", "C2"), default="C1")
    args = parser.parse_args()
    date = next(d for d in common.TRAINING if common.DAYS[d] == args.day)
    t = common.dejitter(common.load_split("training")[date]["t"])
    th = dict(common.hours(t))[args.hour]
    rate = len(th) / 3600
    lam = np.repeat(moving_average_trend(per_second_counts(th, 3600)), int(round(1 / BIN_S)))
    ref = json.loads(Path("traffic/reference/azure_code_burstiness.json").read_text())
    model = load_candidate(ref, args.candidate)
    zero = BurstinessModel("poisson", 0.0, 0.0, (1.0,), (1.0,), 0.0, 1e12)
    gen = cox_arrivals(
        SimpleNamespace(burstiness=model), lam, np.random.default_rng(1), "edge", 3600.0
    )  # type: ignore[arg-type]
    poi = cox_arrivals(
        SimpleNamespace(burstiness=zero), lam, np.random.default_rng(2), "edge", 3600.0
    )  # type: ignore[arg-type]
    print(json.dumps({"day": args.day, "hour": args.hour, "rate": rate,
                      "azure": describe(th, rate), args.candidate: describe(gen, rate),
                      "poisson": describe(poi, rate)}, indent=1))  # fmt: skip


if __name__ == "__main__":
    main()
