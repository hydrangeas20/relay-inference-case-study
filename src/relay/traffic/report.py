"""Print the traffic model's checks against the Azure reference data.

Usage: uv run python -m relay.traffic.report [--peak-rps 300] [--seed 1]

Generates an hour of arrivals around Relay's peak (at a high rate so the statistics
are stable) and compares its burstiness with the Azure fit; checks the envelope's
peak/trough ratio against Azure's weekdays. Exits non-zero if a check fails.
"""

from __future__ import annotations

import argparse
import json
import sys

import numpy as np

from relay.config import get_settings
from relay.traffic.check import check_envelope, rate_cv_by_window
from relay.traffic.generate import TraceSpec, arrival_times
from relay.traffic.model import load_model

BURSTINESS_TOLERANCE = 0.03  # absolute difference in rate CV at each window size


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--peak-rps", type=float, default=300.0)
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args(argv)

    settings = get_settings()
    model = load_model(settings.traffic_model)
    root = settings.traffic_model.parent
    ok = True

    env = check_envelope(model, root / "reference" / "azure_code_hourly.csv")
    ok &= env.passed
    print(f"envelope: {'PASS' if env.passed else 'FAIL'}")
    print(f"  peak/trough {env.model_peak_to_trough}x "
          f"(Azure Mon-Thu {env.azure_weekday_min}x-{env.azure_weekday_max}x)")  # fmt: skip
    print(
        f"  peak hour {env.model_peak_hour_utc}:00 UTC, trough {env.model_trough_hour_utc}:00 UTC"
    )
    print(f"  full-scale peak {model.peak_interactive_rps():.0f} interactive rps")

    peak_h = int(np.argmax(model.hourly_shape()))
    spec = TraceSpec(
        kind="window",
        peak_rps=args.peak_rps,
        seed=args.seed,
        start_utc_s=peak_h * 3600 - 1800,
        duration_s=3600,
    )
    scale = spec.peak_rps / model.peak_interactive_rps()
    times, _ = arrival_times(model, spec, scale, np.random.default_rng(args.seed))
    generated = rate_cv_by_window(times, spec.duration_s)
    reference = json.loads((root / "reference" / "azure_code_burstiness.json").read_text())
    print("burstiness (relative rate fluctuation by window):")
    for row in reference["fit"]:
        w = int(row["window_s"])
        diff = abs(generated[w] - row["observed_rate_cv"])
        passed = diff <= BURSTINESS_TOLERANCE
        ok &= passed
        print(f"  {w:>3}s  generated {generated[w]:.3f}  Azure {row['observed_rate_cv']:.3f}"
              f"  {'PASS' if passed else 'FAIL'}")  # fmt: skip
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
