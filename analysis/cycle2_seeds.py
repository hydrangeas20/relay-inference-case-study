"""Deterministic, non-overlapping seed streams for Cycle 2 candidate work (Amendment 3, A3.6).

seed = first 8 bytes (big-endian) of SHA-256("namespace|i1|i2|..."), used as
numpy.random.default_rng(seed). Separate namespaces keep the streams apart; tests
enumerate every planned seed and require them all to be distinct.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator

import numpy as np

NAMESPACES = {
    "D_calibration": "relay/cycle2/D/calibration/v1",
    "D_validation": "relay/cycle2/D/validation/v1",
    "poisson_validation": "relay/cycle2/poisson-control/validation/v1",
}
CALIBRATION_REPLICATES = 3
VALIDATION_REPLICATES = 20
CELLS = 4


def derive_seed(namespace: str, *indices: object) -> int:
    key = "|".join([namespace, *(str(i) for i in indices)]).encode()
    return int.from_bytes(hashlib.sha256(key).digest()[:8], "big")


def rng(namespace: str, *indices: object) -> np.random.Generator:
    return np.random.default_rng(derive_seed(namespace, *indices))


def calibration_seed(fit: str, day: str, hour: int, replicate: int) -> int:
    """fit: 'all', a held-out day, or 'without-band-<label>' (rate-band holdout fits)."""
    if not 0 <= replicate < CALIBRATION_REPLICATES:
        raise ValueError(replicate)
    return derive_seed(NAMESPACES["D_calibration"], fit, day, hour, replicate)


def validation_seed(stream: str, heldout: str, hour: int, cell: int, replicate: int) -> int:
    """stream: 'D' or 'poisson'."""
    if not (0 <= cell < CELLS and 0 <= replicate < VALIDATION_REPLICATES):
        raise ValueError((cell, replicate))
    if stream not in ("D", "poisson"):
        raise ValueError(stream)
    ns = NAMESPACES["D_validation" if stream == "D" else "poisson_validation"]
    return derive_seed(ns, heldout, hour, cell, replicate)


def planned_seeds(
    days: tuple[str, ...], fits: tuple[str, ...], hours: range = range(24)
) -> Iterator[tuple[str, int]]:
    """Every seed the D procedure can use, over a superset of hours, tagged by stream."""
    for fit in fits:
        for day in days:
            for h in hours:
                for r in range(CALIBRATION_REPLICATES):
                    yield "D_calibration", calibration_seed(fit, day, h, r)
    for stream in ("D", "poisson"):
        for heldout in days:
            for h in hours:
                for c in range(CELLS):
                    for r in range(VALIDATION_REPLICATES):
                        yield f"{stream}_validation", validation_seed(stream, heldout, h, c, r)
