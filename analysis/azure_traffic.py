"""Derive the traffic-model reference data from Azure's public LLM inference trace.

Usage: uv run python analysis/azure_traffic.py [--csv path/to/AzureLLMInferenceTrace_code_1week.csv]

Downloads the 2024 one-week code trace (~690 MB) if no path is given, then writes
three small derived files to traffic/reference/ (these are committed):

  azure_code_hourly.csv       requests per hour for the week (168 rows)
  azure_code_burstiness.json  short-timescale rate fluctuation, fitted per ADR-0004
  azure_code_sizes.csv        20,000 sampled (context tokens, generated tokens) pairs

Source: Azure LLM inference trace 2024, CC-BY 4.0.
  Stojkovic et al., "DynamoLLM: Designing LLM Inference Clusters for Performance
  and Energy Efficiency", HPCA 2025. https://github.com/Azure/AzurePublicDataset
"""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

URL = (
    "https://github.com/Azure/AzurePublicDataset/releases/download/"
    "dataset-llm-2024/AzureLLMInferenceTrace_code_1week.csv"
)
OUT = Path("traffic/reference")
DETREND_WINDOW_S = 600  # rate changes slower than this belong to the daily envelope
FIT_WINDOWS_S = (1, 2, 5, 10, 30, 60)
MIN_HOURLY_RATE = 10.0  # only fit on hours busy enough for the statistics to be stable
SIZE_SAMPLE = 20_000
SEED = 20240510


def load(csv_path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray, datetime]:
    """Seconds since the first midnight (UTC), context tokens, generated tokens."""
    ts: list[float] = []
    ctx: list[int] = []
    gen: list[int] = []
    start: datetime | None = None
    with csv_path.open() as f:
        next(f)
        for line in f:
            stamp, c, g = line.rstrip().rsplit(",", 2)
            t = datetime.fromisoformat(stamp)
            if start is None:
                start = t.replace(hour=0, minute=0, second=0, microsecond=0)
            ts.append((t - start).total_seconds())
            ctx.append(int(c))
            gen.append(int(g))
    assert start is not None
    order = np.argsort(ts)
    return np.asarray(ts)[order], np.asarray(ctx)[order], np.asarray(gen)[order], start


def hourly(ts: np.ndarray, start: datetime) -> list[dict[str, object]]:
    counts = np.bincount((ts // 3600).astype(int))
    rows = []
    for h, n in enumerate(counts):
        t = datetime.fromtimestamp(start.timestamp() + h * 3600, UTC)
        rows.append({"hour_utc": t.strftime("%Y-%m-%dT%H:00Z"), "weekday": t.strftime("%a"),
                     "requests": int(n)})  # fmt: skip
    return rows


def rate_cv2_by_window(t_hour: np.ndarray) -> dict[int, float]:
    """Squared relative fluctuation of the *rate* at each window size, Poisson noise removed.

    Counts per second are compared with a moving-average trend. For window W,
    Z = (count - expected) / expected has Var(Z) = CV_rate(W)^2 + 1/expected, so
    CV_rate(W)^2 is estimated as mean(Z^2 - 1/expected).
    """
    per_s = np.bincount(t_hour.astype(int), minlength=3600)[:3600].astype(float)
    k = DETREND_WINDOW_S
    pad = np.pad(per_s, (k // 2, k - k // 2 - 1), mode="edge")
    trend = np.convolve(pad, np.ones(k) / k, mode="valid")
    out: dict[int, float] = {}
    for w in FIT_WINDOWS_S:
        n = 3600 // w
        c = per_s[: n * w].reshape(n, w).sum(axis=1)
        e = trend[: n * w].reshape(n, w).sum(axis=1)
        z2 = ((c - e) / e) ** 2 - 1.0 / e
        out[w] = float(np.mean(z2))
    return out


def ou_cv2(w: np.ndarray, sigma2: float, tau: float) -> np.ndarray:
    """Relative variance of a window-averaged rate with exponential autocorrelation."""
    x = w / tau
    return sigma2 * 2.0 * (x - 1.0 + np.exp(-x)) / x**2


def fit_burstiness(ts: np.ndarray) -> dict[str, object]:
    per_hour: list[dict[int, float]] = []
    for h in range(int(ts.max() // 3600) + 1):
        t = ts[(ts >= h * 3600) & (ts < (h + 1) * 3600)] - h * 3600
        if len(t) / 3600 >= MIN_HOURLY_RATE:
            per_hour.append(rate_cv2_by_window(t))
    windows = np.array(FIT_WINDOWS_S, dtype=float)
    observed = np.array([np.median([h[w] for h in per_hour]) for w in FIT_WINDOWS_S])
    best: tuple[float, float, float] | None = None
    for tau in np.geomspace(0.1, 600, 400):
        shape = ou_cv2(windows, 1.0, tau)
        sigma2 = float(np.exp(np.mean(np.log(np.clip(observed, 1e-9, None)) - np.log(shape))))
        err = float(np.sum((np.log(np.clip(observed, 1e-9, None)) - np.log(sigma2 * shape)) ** 2))
        if best is None or err < best[0]:
            best = (err, sigma2, float(tau))
    assert best is not None
    _, sigma2, tau = best
    fitted = ou_cv2(windows, sigma2, tau)
    return {
        "model": "log-rate Ornstein-Uhlenbeck (Cox process)",
        "rate_relative_std": round(float(np.sqrt(sigma2)), 4),
        "correlation_time_s": round(tau, 3),
        "hours_used": len(per_hour),
        "detrend_window_s": DETREND_WINDOW_S,
        "fit": [
            {
                "window_s": int(w),
                "observed_rate_cv": round(float(np.sqrt(max(o, 0))), 4),
                "fitted_rate_cv": round(float(np.sqrt(f)), 4),
            }  # fmt: skip
            for w, o, f in zip(windows, observed, fitted, strict=True)
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path)
    args = parser.parse_args()
    csv_path = args.csv
    if csv_path is None:
        csv_path = Path("data/azure/AzureLLMInferenceTrace_code_1week.csv")
        if not csv_path.exists():
            csv_path.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(["curl", "-sSL", "-o", str(csv_path), URL], check=True)

    ts, ctx, gen, start = load(csv_path)
    OUT.mkdir(parents=True, exist_ok=True)

    rows = hourly(ts, start)
    with (OUT / "azure_code_hourly.csv").open("w") as f:
        f.write("hour_utc,weekday,requests\n")
        f.writelines(f"{r['hour_utc']},{r['weekday']},{r['requests']}\n" for r in rows)

    burst = fit_burstiness(ts)
    (OUT / "azure_code_burstiness.json").write_text(json.dumps(burst, indent=2) + "\n")

    rng = np.random.default_rng(SEED)
    idx = np.sort(rng.choice(len(ctx), size=SIZE_SAMPLE, replace=False))
    with (OUT / "azure_code_sizes.csv").open("w") as f:
        f.write("context_tokens,generated_tokens\n")
        f.writelines(f"{int(c)},{int(g)}\n" for c, g in zip(ctx[idx], gen[idx], strict=True))

    print(json.dumps(burst, indent=2))


if __name__ == "__main__":
    main()
