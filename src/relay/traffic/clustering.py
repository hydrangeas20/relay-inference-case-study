"""The `clustered` sensitivity variant (ADR-0005 D2).

Canonical traffic has no sub-second structure. This variant adds Azure's *excess*
sub-millisecond clustering, and deliberately not its unexplained 250 ms periodic
pattern: each canonical arrival becomes a cluster parent with probability 1/m, and
each parent brings a geometric number of extra requests (cluster size mean m) at
gaps drawn from Azure's within-cluster gap distribution. The mean rate is preserved.

m depends on the rate (interpolated in log-rate between Azure's training bands and
held at the ends). The statistics come from raw Azure timestamps, whose semantics
are unresolved, so this variant is for sensitivity analysis only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class ClusteringModel:
    band_rates: tuple[float, ...]
    mean_sizes: tuple[float, ...]
    gap_quantiles_s: tuple[float, ...]

    def mean_size(self, lam: np.ndarray) -> np.ndarray:
        x = np.log(np.asarray(self.band_rates))
        y = np.asarray(self.mean_sizes)
        lam = np.clip(np.asarray(lam, dtype=float), self.band_rates[0], self.band_rates[-1])
        result: np.ndarray = np.interp(np.log(lam), x, y)
        return result

    def sample_gaps(self, rng: np.random.Generator, n: int) -> np.ndarray:
        q = np.asarray(self.gap_quantiles_s)
        u = rng.random(n) * (len(q) - 1)
        result: np.ndarray = np.interp(u, np.arange(len(q)), q)
        return result


def load_clustering(reference: dict[str, Any]) -> ClusteringModel:
    bands = reference["bands"]
    return ClusteringModel(
        band_rates=tuple(float(b["median_rate"]) for b in bands),
        mean_sizes=tuple(float(b["mean_cluster_size"]) for b in bands),
        gap_quantiles_s=tuple(float(x) for x in reference["within_cluster_gap_quantiles_s"]),
    )


def cluster(
    model: ClusteringModel,
    times: np.ndarray,
    lam_at: np.ndarray,
    rng: np.random.Generator,
    duration_s: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Turn canonical arrivals into clustered ones.

    Returns (times, parent_index): each output arrival's index into `times`, so callers
    can carry per-arrival attributes (e.g. workload) from parent to children.
    """
    m = model.mean_size(lam_at)
    is_parent = rng.random(len(times)) < 1.0 / m
    parents = np.flatnonzero(is_parent)
    # Geometric cluster size K >= 1 with mean m: K - 1 extra requests per parent.
    extra = rng.geometric(1.0 / m[parents]) - 1
    out_t = [times[parents]]
    out_i = [parents]
    if extra.sum():
        owner = np.repeat(parents, extra)
        # Children sit after their parent at cumulative within-cluster gaps.
        starts = np.cumsum(extra) - extra
        gaps = model.sample_gaps(rng, int(extra.sum()))
        cum = np.cumsum(gaps)
        base = np.repeat(np.concatenate([[0.0], cum])[starts], extra)
        offsets = cum - base
        out_t.append(times[owner] + offsets)
        out_i.append(owner)
    t = np.concatenate(out_t)
    i = np.concatenate(out_i)
    order = np.argsort(t, kind="stable")
    t, i = t[order], i[order]
    keep = t < duration_s
    return t[keep], i[keep]
