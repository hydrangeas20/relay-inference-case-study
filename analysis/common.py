"""Shared data access for the Azure analyses, with the holdout guard.

Data split (docs/validation/phase-2-preregistration.md):

  training    Fri 2024-05-10 .. Tue 2024-05-14
  validation  Thu 2024-05-16   (model selection)
  holdout     Wed 2024-05-15   (evaluated exactly once, only when authorised)

Holdout rows are discarded by their date prefix *before* any timestamp or token
count is parsed, so no statistic can be computed on them unless a caller passes
allow_holdout=True. Only the final evaluation script does that, behind a
command-line flag.
"""

from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

RAW_URL = (
    "https://github.com/Azure/AzurePublicDataset/releases/download/"
    "dataset-llm-2024/AzureLLMInferenceTrace_code_1week.csv"
)
RAW_SHA256 = "71de5c55cbc35f8f1ed0b6b7806b4cd1e9764b0058469725a6aac98023a1448f"
RAW_ROWS = 16_803_695
RAW_PATH = Path("data/azure/AzureLLMInferenceTrace_code_1week.csv")
CACHE_DIR = Path("data/azure/cache")

DAYS = {
    "2024-05-10": "Fri",
    "2024-05-11": "Sat",
    "2024-05-12": "Sun",
    "2024-05-13": "Mon",
    "2024-05-14": "Tue",
    "2024-05-15": "Wed",
    "2024-05-16": "Thu",
}
TRAINING = ("2024-05-10", "2024-05-11", "2024-05-12", "2024-05-13", "2024-05-14")
VALIDATION = ("2024-05-16",)
HOLDOUT = ("2024-05-15",)
SPLITS = {"training": TRAINING, "validation": VALIDATION, "holdout": HOLDOUT}

DEJITTER_PERIOD_S = 0.25
DEJITTER_SEED = 20260928
MIN_ELIGIBLE_RATE = 3.0  # rps; hours below this aren't used for burstiness
RATE_BANDS = ((3.0, 10.0), (10.0, 30.0), (30.0, 60.0), (60.0, 120.0))


class HoldoutAccessError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 22), b""):
            h.update(block)
    return h.hexdigest()


def verify_raw(path: Path = RAW_PATH) -> None:
    actual = sha256_file(path)
    if actual != RAW_SHA256:
        raise ValueError(f"{path} has SHA-256 {actual}, expected {RAW_SHA256}")


def _parse(raw_path: Path, dates: tuple[str, ...]) -> dict[str, dict[str, np.ndarray]]:
    wanted = set(dates)
    parts: dict[str, list[pd.DataFrame]] = {d: [] for d in dates}
    for chunk in pd.read_csv(raw_path, chunksize=2_000_000, dtype=str):
        day = chunk["TIMESTAMP"].str.slice(0, 10)
        keep = chunk[day.isin(wanted)]  # other days are dropped before any parsing
        for d in dates:
            sel = keep[keep["TIMESTAMP"].str.startswith(d)]
            if len(sel):
                parts[d].append(sel)
    out: dict[str, dict[str, np.ndarray]] = {}
    for d in dates:
        df = pd.concat(parts[d]) if parts[d] else pd.DataFrame(columns=["TIMESTAMP"])
        ts = pd.to_datetime(df["TIMESTAMP"], utc=True, format="ISO8601")
        midnight = pd.Timestamp(date.fromisoformat(d), tz="UTC")
        secs = (ts - midnight).dt.total_seconds().to_numpy()
        order = np.argsort(secs, kind="stable")
        out[d] = {
            "t": secs[order],
            "ctx": df["ContextTokens"].astype(int).to_numpy()[order],
            "gen": df["GeneratedTokens"].astype(int).to_numpy()[order],
        }
    return out


def load_split(
    split: str, raw_path: Path = RAW_PATH, allow_holdout: bool = False
) -> dict[str, dict[str, np.ndarray]]:
    """Per-day arrays (seconds after that day's UTC midnight, sorted) for one split."""
    if split not in SPLITS:
        raise ValueError(f"unknown split {split!r}")
    if split == "holdout" and not allow_holdout:
        raise HoldoutAccessError(
            "the Wednesday holdout is evaluated exactly once, only when authorised "
            "(docs/validation/phase-2-preregistration.md)"
        )
    dates = SPLITS[split]
    cache = CACHE_DIR / f"{split}.npz"
    if cache.exists():
        z = np.load(cache)
        return {d: {k: z[f"{d}/{k}"] for k in ("t", "ctx", "gen")} for d in dates}
    verify_raw(raw_path)
    data = _parse(raw_path, dates)
    cache.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        cache, **{f"{d}/{k}": v for d, arrs in data.items() for k, v in arrs.items()}
    )
    return data


def dejitter(t: np.ndarray, seed: int = DEJITTER_SEED) -> np.ndarray:
    """Re-draw each timestamp uniformly within its 250 ms interval (ADR-0005, sub-second)."""
    rng = np.random.default_rng(seed)
    base = np.floor(t / DEJITTER_PERIOD_S) * DEJITTER_PERIOD_S
    return np.sort(base + rng.random(len(t)) * DEJITTER_PERIOD_S)


def hours(t: np.ndarray) -> list[tuple[int, np.ndarray]]:
    """(hour of day, arrival times relative to the start of that hour) for 24 UTC hours."""
    edges = np.searchsorted(t, np.arange(25) * 3600.0)
    return [(h, t[edges[h] : edges[h + 1]] - h * 3600.0) for h in range(24)]


def band_of(rate: float) -> int | None:
    for i, (lo, hi) in enumerate(RATE_BANDS):
        if lo <= rate < hi:
            return i
    return None
