"""Relay's traffic model: when requests arrive, how bursty they are, and how big.

Three layers (ADR-0004, amended by ADR-0005):
  1. Envelope: the weekday 24-hour shape (ASSUMED, plausibility-checked against Azure).
  2. Burstiness: a Cox process whose relative fluctuation depends on the trace's own
     expected rate inside Azure's observed range, and on a named scenario outside it
     (relay.traffic.burstiness). An optional clustered variant adds sub-second
     clustering for sensitivity analysis (relay.traffic.clustering).
  3. Sizes: completion prompt/output token targets resampled from Azure (training days);
     agent and indexing sizes are Relay assumptions.
"""

from __future__ import annotations

import csv
import hashlib
import json
import tomllib
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from relay.traffic.burstiness import BurstinessModel, load_candidate
from relay.traffic.clustering import ClusteringModel, load_clustering

SECONDS_PER_DAY = 86_400


@dataclass(frozen=True)
class Region:
    name: str
    share: float
    center_utc_h: float
    width_h: float


@dataclass(frozen=True)
class TrafficModel:
    daily_active_users: int
    active_hours_per_day: float
    completions_per_active_hour: float
    agent_turns_per_active_hour: float
    floor: float
    regions: tuple[Region, ...]
    burstiness: BurstinessModel
    clustering: ClusteringModel
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
    cluster_path = root / cfg["burstiness"]["clustering_reference"]
    sizes_path = root / cfg["sizes"]["completion_reference"]

    digest = hashlib.sha256(raw)
    for path in (burst_path, cluster_path, sizes_path):
        digest.update(path.read_bytes())

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
        burstiness=load_candidate(burst, str(cfg["burstiness"]["candidate"])),
        clustering=load_clustering(json.loads(cluster_path.read_text())),
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
