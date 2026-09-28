"""Relay's traffic model: when requests arrive, how bursty they are, and how big.

Three layers (ADR-0004):
  1. Envelope: the weekday 24-hour shape (decision 1C), in requests/second at full scale.
  2. Burstiness: a Cox process. The envelope rate is multiplied by exp(X - s^2/2),
     where X is an Ornstein-Uhlenbeck process fitted to Azure's code trace (2C).
     The multiplier is relative, so it survives scaling down to one GPU.
  3. Sizes: completion prompt/output lengths resampled from Azure (3B); agent and
     indexing sizes are Relay assumptions.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import tomllib
from dataclasses import dataclass
from pathlib import Path

import numpy as np

SECONDS_PER_DAY = 86_400


@dataclass(frozen=True)
class Region:
    name: str
    share: float
    center_utc_h: float
    width_h: float


@dataclass(frozen=True)
class Burstiness:
    rate_relative_std: float
    correlation_time_s: float


@dataclass(frozen=True)
class TrafficModel:
    daily_active_users: int
    active_hours_per_day: float
    completions_per_active_hour: float
    agent_turns_per_active_hour: float
    floor: float
    regions: tuple[Region, ...]
    burstiness: Burstiness
    indexing_jobs_per_day: int
    indexing_window_start_utc_h: float
    indexing_window_minutes: float
    indexing_files_per_job: tuple[int, int]
    indexing_chunk_chars: int
    completion_sizes: np.ndarray  # shape (n, 2): context tokens, generated tokens
    chars_per_token: float
    completion_context_files: tuple[int, int]
    completion_suffix_chars: tuple[int, int]
    agent_context_chars: tuple[int, int]
    agent_max_tokens: tuple[int, int]
    sha256: str  # of the config and reference files: identifies the model in traces

    # --- envelope -----------------------------------------------------------------

    def shape(self, t_s: np.ndarray) -> np.ndarray:
        """Relative weekday activity at seconds-since-midnight UTC, peak = 1."""
        return self._shape_raw(t_s) / self._shape_peak()

    def _shape_raw(self, t_s: np.ndarray) -> np.ndarray:
        h = (np.asarray(t_s, dtype=float) / 3600.0) % 24.0
        bumps = np.zeros_like(h)
        for r in self.regions:
            d = (h - r.center_utc_h + 12.0) % 24.0 - 12.0  # wrap around midnight
            bumps += r.share * np.exp(-0.5 * (d / r.width_h) ** 2)
        peak = self._bump_peak()
        return self.floor + (1.0 - self.floor) * bumps / peak

    def _bump_peak(self) -> float:
        h = np.arange(0, 24, 1 / 360)
        bumps = np.zeros_like(h)
        for r in self.regions:
            d = (h - r.center_utc_h + 12.0) % 24.0 - 12.0
            bumps += r.share * np.exp(-0.5 * (d / r.width_h) ** 2)
        return float(bumps.max())

    def _shape_peak(self) -> float:
        return float(self._shape_raw(np.arange(0, SECONDS_PER_DAY, 10.0)).max())

    def _shape_daily_integral_s(self) -> float:
        t = np.arange(0, SECONDS_PER_DAY, 10.0)
        return float(self.shape(t).sum() * 10.0)

    def daily_requests(self) -> dict[str, float]:
        active_hours = self.daily_active_users * self.active_hours_per_day
        return {
            "completion": active_hours * self.completions_per_active_hour,
            "agent": active_hours * self.agent_turns_per_active_hour,
        }

    def interactive_rate_rps(self, t_s: np.ndarray) -> dict[str, np.ndarray]:
        """Full-scale requests/second by workload at each time."""
        per_unit = 1.0 / self._shape_daily_integral_s()
        s = self.shape(t_s)
        return {w: n * per_unit * s for w, n in self.daily_requests().items()}

    def peak_interactive_rps(self) -> float:
        t = np.arange(0, SECONDS_PER_DAY, 10.0)
        total = sum(self.interactive_rate_rps(t).values())
        return float(np.max(total))

    def hourly_shape(self) -> np.ndarray:
        """Mean relative activity per UTC hour (24 values), for checking against Azure."""
        t = np.arange(0, SECONDS_PER_DAY, 10.0)
        hours: np.ndarray = self.shape(t).reshape(24, 360).mean(axis=1)
        return hours

    # --- burstiness ---------------------------------------------------------------

    def modulation(self, n_bins: int, dt_s: float, rng: np.random.Generator) -> np.ndarray:
        """Rate multiplier with mean 1, relative std and correlation time from the fit."""
        cv = self.burstiness.rate_relative_std
        s2 = math.log1p(cv * cv)  # lognormal: Var(exp(X)) / E^2 = e^{s^2} - 1 = cv^2
        s = math.sqrt(s2)
        a = math.exp(-dt_s / self.burstiness.correlation_time_s)
        noise = rng.standard_normal(n_bins) * s * math.sqrt(1.0 - a * a)
        x = np.empty(n_bins)
        x[0] = rng.standard_normal() * s
        for i in range(1, n_bins):  # AR(1) recursion; exact OU discretisation
            x[i] = a * x[i - 1] + noise[i]
        result: np.ndarray = np.exp(x - s2 / 2.0)
        return result


def _range(v: list[int]) -> tuple[int, int]:
    lo, hi = int(v[0]), int(v[1])
    if lo > hi:
        raise ValueError(f"range {v} has min > max")
    return lo, hi


def load_model(config_path: Path, root: Path | None = None) -> TrafficModel:
    root = root or config_path.parent.parent
    raw = config_path.read_bytes()
    cfg = tomllib.loads(raw.decode())
    burst_path = root / cfg["burstiness"]["reference"]
    sizes_path = root / cfg["sizes"]["completion_reference"]

    digest = hashlib.sha256(raw)
    digest.update(burst_path.read_bytes())
    digest.update(sizes_path.read_bytes())

    burst = json.loads(burst_path.read_text())
    with sizes_path.open() as f:
        sizes = np.array(
            [(int(r["context_tokens"]), int(r["generated_tokens"])) for r in csv.DictReader(f)],
            dtype=np.int64,
        )

    regions = tuple(Region(**r) for r in cfg["envelope"]["region"])
    if abs(sum(r.share for r in regions) - 1.0) > 1e-9:
        raise ValueError("region shares must sum to 1")
    floor = float(cfg["envelope"]["floor"])
    if not 0.0 <= floor < 1.0:
        raise ValueError("envelope floor must be in [0, 1)")

    ix = cfg["indexing"]
    sz = cfg["sizes"]
    return TrafficModel(
        daily_active_users=int(cfg["users"]["daily_active"]),
        active_hours_per_day=float(cfg["users"]["active_hours_per_day"]),
        completions_per_active_hour=float(cfg["rates"]["completions_per_active_hour"]),
        agent_turns_per_active_hour=float(cfg["rates"]["agent_turns_per_active_hour"]),
        floor=floor,
        regions=regions,
        burstiness=Burstiness(
            rate_relative_std=float(burst["rate_relative_std"]),
            correlation_time_s=float(burst["correlation_time_s"]),
        ),
        indexing_jobs_per_day=int(ix["jobs_per_day"]),
        indexing_window_start_utc_h=float(ix["window_start_utc_h"]),
        indexing_window_minutes=float(ix["window_minutes"]),
        indexing_files_per_job=_range(ix["files_per_job"]),
        indexing_chunk_chars=int(ix["chunk_chars"]),
        completion_sizes=sizes,
        chars_per_token=float(sz["chars_per_token"]),
        completion_context_files=_range(sz["completion_context_files"]),
        completion_suffix_chars=_range(sz["completion_suffix_chars"]),
        agent_context_chars=_range(sz["agent_context_chars"]),
        agent_max_tokens=_range(sz["agent_max_tokens"]),
        sha256=digest.hexdigest(),
    )
