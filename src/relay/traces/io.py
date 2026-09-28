"""Read and write trace files."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from pydantic import TypeAdapter

from relay.traces.schema import TRACE_FORMAT_VERSION, TraceHeader, TraceRequest

_request_adapter: TypeAdapter[TraceRequest] = TypeAdapter(TraceRequest)


class TraceFormatError(ValueError):
    pass


@dataclass(frozen=True)
class Trace:
    header: TraceHeader
    requests: list[TraceRequest]
    sha256: str


def dumps(header: TraceHeader, requests: list[TraceRequest]) -> str:
    lines = [header.model_dump_json()]
    lines += [_request_adapter.dump_json(r).decode() for r in requests]
    return "\n".join(lines) + "\n"


def write_trace(path: Path, header: TraceHeader, requests: list[TraceRequest]) -> str:
    """Write a trace and return its SHA-256."""
    text = dumps(header, requests)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return hashlib.sha256(text.encode()).hexdigest()


def read_trace(path: Path) -> Trace:
    raw = path.read_bytes()
    lines = raw.decode().splitlines()
    if not lines:
        raise TraceFormatError(f"{path} is empty")
    header = TraceHeader.model_validate_json(lines[0])
    if header.format_version != TRACE_FORMAT_VERSION:
        raise TraceFormatError(f"unsupported trace format version {header.format_version}")
    requests = [_request_adapter.validate_json(line) for line in lines[1:] if line.strip()]
    if len(requests) != header.n_requests:
        raise TraceFormatError(f"header says {header.n_requests} requests, found {len(requests)}")
    if any(b.send_at_s < a.send_at_s for a, b in zip(requests, requests[1:], strict=False)):
        raise TraceFormatError("requests must be sorted by send_at_s")
    return Trace(header=header, requests=requests, sha256=hashlib.sha256(raw).hexdigest())
