import json
from pathlib import Path

import numpy as np
import pytest

from relay.traffic.clustering import cluster, load_clustering
from relay.traffic.generate import BIN_S, cox_arrivals
from relay.traffic.model import load_model

ROOT = Path(__file__).resolve().parents[1]
MODEL = load_model(ROOT / "traffic" / "relay.toml")
REF = json.loads((ROOT / "traffic" / "reference" / "azure_code_clustering.json").read_text())


def _canonical(rate: float, seed: int) -> np.ndarray:
    lam = np.full(int(3600 / BIN_S), rate)
    return cox_arrivals(MODEL, lam, np.random.default_rng(seed), None, 3600.0)


def test_canonical_has_no_excess_submillisecond_gaps() -> None:
    rate = 50.0
    t = _canonical(rate, 1)
    assert np.mean(np.diff(t) < 1e-3) == pytest.approx(1 - np.exp(-rate * 1e-3), abs=0.01)


def test_nothing_reproduces_the_250ms_pattern() -> None:
    rate = 50.0
    base = _canonical(rate, 2)
    clustered, _ = cluster(
        MODEL.clustering, base, np.full(len(base), rate), np.random.default_rng(3), 3600.0
    )
    for t in (base, clustered):
        assert np.mean((t % 0.25) >= 0.2) == pytest.approx(0.2, abs=0.01)


def test_clustered_variant_preserves_rate_and_adds_clusters() -> None:
    rate = 50.0
    base = _canonical(rate, 4)
    t, parent = cluster(
        MODEL.clustering, base, np.full(len(base), rate), np.random.default_rng(5), 3600.0
    )
    assert len(t) == pytest.approx(len(base), rel=0.03)
    assert np.all(np.diff(t) >= 0)
    assert np.mean(np.diff(t) < 1e-3) > 3 * np.mean(np.diff(base) < 1e-3)
    assert parent.min() >= 0 and parent.max() < len(base)


def test_mean_cluster_size_follows_the_bands() -> None:
    m = load_clustering(REF)
    rates = [b["median_rate"] for b in REF["bands"]]
    sizes = [b["mean_cluster_size"] for b in REF["bands"]]
    assert np.allclose(m.mean_size(np.array(rates)), sizes)
    assert m.mean_size(np.array([1.0]))[0] == pytest.approx(sizes[0])  # held at the ends
    assert m.mean_size(np.array([500.0]))[0] == pytest.approx(sizes[-1])
    assert REF["source"].startswith("raw timestamps")
