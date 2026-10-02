"""Cycle 2 development data: cache-only, fail-closed (Cycle 2 preregistration, "Data").

Cycle 2 development uses six days (Fri, Sat, Sun, Mon, Tue, Thu) and reads them
ONLY from the existing caches recorded in cycle2_cache_manifest.json. The raw Azure
file (which also contains Wednesday, the final lockbox) must not be opened, hashed,
scanned or used to rebuild anything during Cycle 2.

Usage, as the first thing a Cycle 2 script does:

    import cycle2_data
    cycle2_data.enter_cycle2_mode()
    days = cycle2_data.load_development()

enter_cycle2_mode() blocks, for the rest of the process:
  - common.load_split / common._parse / common.verify_raw (the raw-file paths), and
  - any open of a file named like the raw trace, by any route, through a
    sys.addaudithook hook on the interpreter's "open" event. Patching builtins.open
    isn't enough: libraries such as numpy keep their own reference to io.open.
    Audit hooks can't be removed once installed, so the block holds for the rest
    of the process (tests switch it off with exit_cycle2_mode).
Scope: this process, and processes forked from it (they inherit the hook). A
spawned worker must call enter_cycle2_mode() itself, and shell commands are outside
any Python guard; Cycle 2 code uses neither on data.

load_development() refuses to run outside Cycle 2 mode, refuses a missing cache
(no fallback, no rebuild), and refuses a cache whose SHA-256 or day set differs
from the manifest.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np

import common

MANIFEST = Path(__file__).with_name("cycle2_cache_manifest.json")
DEVELOPMENT_DAYS = (
    "2024-05-10",
    "2024-05-11",
    "2024-05-12",
    "2024-05-13",
    "2024-05-14",
    "2024-05-16",
)
HOLDOUT_DATE = "2024-05-15"
RAW_NAME = common.RAW_PATH.name


class CacheOnlyError(RuntimeError):
    """A Cycle 2 cache is missing, altered or unexpected; nothing falls back to raw data."""


class RawAccessBlocked(RuntimeError):
    """Something tried to touch the raw Azure file during Cycle 2."""


_ACTIVE = False
_ORIGINALS: dict[str, Any] = {}


def _blocked(name: str) -> Callable[..., Any]:
    def fail(*args: Any, **kwargs: Any) -> Any:
        raise RawAccessBlocked(f"{name}: raw Azure data is off-limits during Cycle 2")

    return fail


def _is_raw(path: object) -> bool:
    try:
        return Path(os.fsdecode(path)).name == RAW_NAME  # type: ignore[arg-type]
    except TypeError:
        return False  # file descriptors and the like


_HOOK_INSTALLED = False


def _audit(event: str, args: tuple[Any, ...]) -> None:
    if _ACTIVE and event == "open" and args and _is_raw(args[0]):
        raise RawAccessBlocked(f"open({args[0]!r}): raw Azure data is off-limits during Cycle 2")


def enter_cycle2_mode() -> None:
    """Block every raw-data path for the rest of the process (idempotent)."""
    global _ACTIVE, _HOOK_INSTALLED
    if _ACTIVE:
        return
    if not _HOOK_INSTALLED:
        sys.addaudithook(_audit)
        _HOOK_INSTALLED = True
    _ORIGINALS.update(
        load_split=common.load_split, _parse=common._parse, verify_raw=common.verify_raw
    )
    common.load_split = _blocked("common.load_split")  # type: ignore[assignment]
    common._parse = _blocked("common._parse")  # type: ignore[assignment]
    common.verify_raw = _blocked("common.verify_raw")  # type: ignore[assignment]
    _ACTIVE = True


def exit_cycle2_mode() -> None:
    """Switch the block off (tests only; the audit hook stays installed but inert)."""
    global _ACTIVE
    if not _ACTIVE:
        return
    common.load_split = _ORIGINALS["load_split"]
    common._parse = _ORIGINALS["_parse"]
    common.verify_raw = _ORIGINALS["verify_raw"]
    _ACTIVE = False


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_caches(manifest: Path = MANIFEST, cache_dir: Path = common.CACHE_DIR) -> dict[str, Any]:
    """Check every manifest cache exists, has its recorded hash and holds only its days."""
    spec = json.loads(manifest.read_text())
    for name, entry in spec["files"].items():
        path = cache_dir / name
        if not path.exists():
            raise CacheOnlyError(f"{path} is missing; Cycle 2 never rebuilds caches from raw data")
        digest = _sha256(path)
        if digest != entry["sha256"]:
            raise CacheOnlyError(f"{path}: sha256 {digest} != manifest {entry['sha256']}")
        days = sorted({n.split("/")[0] for n in zipfile.ZipFile(path).namelist()})
        if days != sorted(entry["days"]) or HOLDOUT_DATE in days:
            raise CacheOnlyError(f"{path}: days {days} != manifest {entry['days']}")
    all_days = sorted(d for e in spec["files"].values() for d in e["days"])
    if all_days != sorted(DEVELOPMENT_DAYS):
        raise CacheOnlyError(f"manifest days {all_days} != development days {DEVELOPMENT_DAYS}")
    return dict(spec)


def load_development(
    manifest: Path = MANIFEST, cache_dir: Path = common.CACHE_DIR
) -> dict[str, dict[str, np.ndarray]]:
    """Per-day arrays (t, ctx, gen) for the six development days, from verified caches only."""
    if not _ACTIVE:
        raise CacheOnlyError("call enter_cycle2_mode() first: Cycle 2 loading is fail-closed")
    spec = verify_caches(manifest, cache_dir)
    out: dict[str, dict[str, np.ndarray]] = {}
    for name, entry in spec["files"].items():
        z = np.load(cache_dir / name, allow_pickle=False)
        for d in entry["days"]:
            out[d] = {k: z[f"{d}/{k}"] for k in ("t", "ctx", "gen")}
    return {d: out[d] for d in DEVELOPMENT_DAYS}
