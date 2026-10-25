"""Trace identity (ADR-0005 D7). Three separate concepts:

spec_id           What was requested: the trace specification plus the hashes of its
                  input data (corpus, traffic model). Same request -> same spec_id,
                  whatever code produced it.
generator_sha256  What produced it: the source of every module on the generation path,
                  plus the Python, numpy and pydantic versions. A code or environment
                  change changes it, even when the output doesn't.
trace_id          What was produced: SHA-256 of the request lines. Two traces share a
                  trace_id only if their requests are byte-identical.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import platform
from collections.abc import Iterable
from typing import Any

import numpy as np
import pydantic

# Every relay module whose code can affect a generated trace. tests/test_trace_identity.py
# fails if the generator imports a relay module that isn't listed here.
GENERATOR_MODULES: tuple[str, ...] = (
    "relay.config",
    "relay.corpus.manifest",
    "relay.corpus.store",
    "relay.gateway.templates",
    "relay.prompts",
    "relay.traces.generate",
    "relay.traces.identity",
    "relay.traces.io",
    "relay.traces.schema",
    "relay.traces.sessions",
    "relay.traffic.burstiness",
    "relay.traffic.clustering",
    "relay.traffic.generate",
    "relay.traffic.model",
)


def generator_sha256(modules: Iterable[str] = GENERATOR_MODULES) -> str:
    h = hashlib.sha256()
    for name in sorted(modules):
        mod = importlib.import_module(name)
        path = mod.__file__
        if path is None:
            raise RuntimeError(f"module {name} has no source file")
        h.update(name.encode() + b"\0")
        with open(path, "rb") as f:
            h.update(f.read())
    env = f"python={platform.python_version()};numpy={np.__version__};pydantic={pydantic.VERSION}"
    h.update(env.encode())
    return h.hexdigest()


def spec_id(spec: dict[str, Any]) -> str:
    """Canonical JSON of the requested specification and its input hashes."""
    payload = json.dumps(spec, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def content_trace_id(request_lines: Iterable[str]) -> str:
    h = hashlib.sha256()
    for line in request_lines:
        h.update(line.encode())
        h.update(b"\n")
    return h.hexdigest()
