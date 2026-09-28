"""`make traffic-check`: in-sample consistency checks of the traffic model.

Usage: uv run python -m relay.traffic.report [--seeds 5]

1. Envelope: the weekday peak/trough ratio against Azure's training weekdays
   (a plausibility check on one number).
2. Burstiness, in-sample: for each Azure rate band, generate one hour of canonical
   traffic at the band's median rate and compare its rate-fluctuation curve with the
   band's pooled curve from the *training* days (SIMULATED vs AZURE-DERIVED). This shows
   the generator implements the fitted model; it is not out-of-sample validation, which
   is preregistered separately (docs/validation/phase-2-preregistration.md).

Exits non-zero if a check with a defined tolerance fails.
"""

from __future__ import annotations

import argparse
import json
import sys

import numpy as np

from relay.config import get_settings
from relay.traffic.check import check_envelope
from relay.traffic.generate import BIN_S, cox_arrivals
from relay.traffic.model import load_model
from relay.traffic.stats import WINDOWS_S, rate_cv2

BAND_TOLERANCE_KEYS = ("3-10", "10-30", "30-60", "60-120")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, default=5)
    args = parser.parse_args(argv)

    settings = get_settings()
    model = load_model(settings.traffic_model)
    root = settings.traffic_model.parent
    reference = json.loads((root / "reference" / "azure_code_burstiness.json").read_text())
    ok = True

    env = check_envelope(model, root / "reference" / "azure_code_hourly.csv")
    ok &= env.passed
    print(f"envelope: {'PASS' if env.passed else 'FAIL'}")
    print(
        f"  peak/trough {env.model_peak_to_trough}x (CALCULATED); Azure training weekdays "
        f"{env.azure_weekday_min}x-{env.azure_weekday_max}x (AZURE-DERIVED)"
    )
    print(f"  smooth-curve peak {model.peak_interactive_rps():.0f} interactive rps (CALCULATED)")

    b = model.burstiness
    print(
        f"burstiness {b.name}: sigma = {b.a:.4f} * rate^{b.b:.4f} "
        f"within {b.rate_min}-{b.rate_max} rps (AZURE-DERIVED, training days)"
    )
    print(
        "  in-sample: generated (mean of seeds) vs training pooled curve, windows", list(WINDOWS_S)
    )
    for band, key in zip(reference["bands"], BAND_TOLERANCE_KEYS, strict=True):
        rate = float(band["median_rate"])
        lam = np.full(int(3600 / BIN_S), rate)
        curves = []
        for seed in range(1, args.seeds + 1):
            t = cox_arrivals(model, lam, np.random.default_rng(seed), None, 3600.0)
            curves.append(rate_cv2(t, 3600))
        generated = np.sqrt(np.clip(np.mean(curves, axis=0), 0, None))
        observed = np.asarray(band["pooled_cv"])
        diff = float(np.max(np.abs(generated - observed)))
        tol_entry = reference["tolerances"].get(key)
        tol = tol_entry["tolerance"] if tol_entry and len(tol_entry["days"]) >= 3 else None
        if tol is None:
            verdict = "no tolerance (pending O2)"
        else:
            passed = diff <= tol
            ok &= passed
            verdict = f"{'PASS' if passed else 'FAIL'} (tolerance {tol})"
        print(f"  {key:>6} rps at {rate:6.2f}: max |diff| {diff:.4f}  {verdict}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
