"""Cycle 2 is cache-only and fail-closed: the raw file (which holds Wednesday) is never touched."""

import builtins
import hashlib
import json
import os
import re
import sys
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "analysis"))
import common  # noqa: E402
import cycle2_data  # noqa: E402


@pytest.fixture
def cycle2_mode() -> Iterator[None]:
    cycle2_data.enter_cycle2_mode()
    try:
        yield
    finally:
        cycle2_data.exit_cycle2_mode()


def _fake_caches(tmp_path: Path) -> Path:
    """Caches shaped like the real ones, with a manifest recording their hashes."""
    files = {
        "training.npz": ["2024-05-10", "2024-05-11", "2024-05-12", "2024-05-13", "2024-05-14"],
        "validation.npz": ["2024-05-16"],
    }
    manifest: dict[str, dict[str, object]] = {"files": {}}
    for name, days in files.items():
        arrays = {f"{d}/{k}": np.arange(3, dtype=float) for d in days for k in ("t", "ctx", "gen")}
        np.savez(tmp_path / name, **arrays)  # type: ignore[arg-type]
        digest = hashlib.sha256((tmp_path / name).read_bytes()).hexdigest()
        manifest["files"][name] = {"sha256": digest, "days": days}
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    return tmp_path / "manifest.json"


def test_loading_refuses_outside_cycle2_mode(tmp_path: Path) -> None:
    with pytest.raises(cycle2_data.CacheOnlyError):
        cycle2_data.load_development(_fake_caches(tmp_path), tmp_path)


def test_loads_the_six_development_days_from_verified_caches(
    tmp_path: Path, cycle2_mode: None
) -> None:
    days = cycle2_data.load_development(_fake_caches(tmp_path), tmp_path)
    assert tuple(days) == cycle2_data.DEVELOPMENT_DAYS
    assert cycle2_data.HOLDOUT_DATE not in days


def test_missing_cache_fails_closed_without_touching_raw(tmp_path: Path, cycle2_mode: None) -> None:
    manifest = _fake_caches(tmp_path)
    (tmp_path / "validation.npz").unlink()
    with pytest.raises(cycle2_data.CacheOnlyError, match="never rebuilds"):
        cycle2_data.load_development(manifest, tmp_path)


def test_altered_cache_is_rejected(tmp_path: Path, cycle2_mode: None) -> None:
    manifest = _fake_caches(tmp_path)
    np.savez(tmp_path / "validation.npz", **{"2024-05-16/t": np.zeros(1)})
    with pytest.raises(cycle2_data.CacheOnlyError, match="sha256"):
        cycle2_data.load_development(manifest, tmp_path)


def test_cache_with_a_holdout_day_is_rejected(tmp_path: Path, cycle2_mode: None) -> None:
    manifest = _fake_caches(tmp_path)
    arrays = {f"2024-05-15/{k}": np.zeros(1) for k in ("t", "ctx", "gen")}
    arrays |= {f"2024-05-16/{k}": np.zeros(1) for k in ("t", "ctx", "gen")}
    np.savez(tmp_path / "validation.npz", **arrays)  # type: ignore[arg-type]
    spec = json.loads(manifest.read_text())
    spec["files"]["validation.npz"]["sha256"] = hashlib.sha256(
        (tmp_path / "validation.npz").read_bytes()
    ).hexdigest()
    manifest.write_text(json.dumps(spec))
    with pytest.raises(cycle2_data.CacheOnlyError, match="days"):
        cycle2_data.load_development(manifest, tmp_path)


def test_raw_loader_paths_are_blocked(tmp_path: Path, cycle2_mode: None) -> None:
    for call in (
        lambda: common.load_split("training"),
        lambda: common.load_split("holdout", allow_holdout=True),
        lambda: common.verify_raw(),
        lambda: common._parse(tmp_path / "x.csv", ("2024-05-14",)),
    ):
        with pytest.raises(cycle2_data.RawAccessBlocked):
            call()


@pytest.fixture
def dummy_raw_then_mode(tmp_path: Path) -> Iterator[Path]:
    """A dummy file with the raw trace's name (not the real data), then Cycle 2 mode."""
    raw = tmp_path / common.RAW_PATH.name
    raw.write_text("TIMESTAMP,ContextTokens,GeneratedTokens\n")
    cycle2_data.enter_cycle2_mode()
    try:
        yield raw
    finally:
        cycle2_data.exit_cycle2_mode()


def test_opening_the_raw_file_by_any_route_is_blocked(
    tmp_path: Path, dummy_raw_then_mode: Path
) -> None:
    raw = dummy_raw_then_mode
    for opener in (
        lambda: builtins.open(raw, "rb"),  # noqa: SIM115 (expected to raise)
        lambda: open(str(raw)),  # noqa: SIM115
        lambda: os.open(raw, os.O_RDONLY),
        lambda: raw.open("rb"),
        lambda: np.loadtxt(raw),
        lambda: np.genfromtxt(raw),
        lambda: raw.read_bytes(),
    ):
        with pytest.raises(cycle2_data.RawAccessBlocked):
            opener()
    (tmp_path / "other.txt").write_text("fine")
    assert (tmp_path / "other.txt").read_text() == "fine"  # ordinary files still work


def test_mode_is_restored_after_tests(tmp_path: Path) -> None:
    assert common.load_split.__name__ == "load_split"
    raw = tmp_path / common.RAW_PATH.name
    raw.write_text("x")  # the hook is inert outside Cycle 2 mode
    assert raw.read_text() == "x"


def test_manifest_records_only_development_days() -> None:
    spec = json.loads(cycle2_data.MANIFEST.read_text())
    days = sorted(d for e in spec["files"].values() for d in e["days"])
    assert days == sorted(cycle2_data.DEVELOPMENT_DAYS)
    assert cycle2_data.HOLDOUT_DATE not in json.dumps(spec["files"])


@pytest.mark.skipif(
    not (common.CACHE_DIR / "training.npz").exists(), reason="local caches not present (CI)"
)
def test_local_caches_match_the_manifest() -> None:
    os.chdir(ROOT)
    cycle2_data.verify_caches()


def test_cycle2_code_never_references_raw_data_paths() -> None:
    """Static check: only the guard itself may name the raw-file entry points."""
    pattern = re.compile(r"\b(RAW_PATH|RAW_URL|load_split|verify_raw|_parse|azure_download)\b")
    for path in sorted((ROOT / "analysis").glob("*.py")):
        if not (path.name.startswith("cycle2") or path.name == "criterion_audit.py"):
            continue
        if path.name == "cycle2_data.py":
            continue
        hits = pattern.findall(path.read_text())
        assert not hits, f"{path.name} references {sorted(set(hits))}"
