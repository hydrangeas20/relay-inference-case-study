"""Read and write trace files."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from pydantic import TypeAdapter

from relay.traces.identity import content_trace_id
from relay.traces.schema import SUPPORTED_FORMAT_VERSIONS, TraceHeader, TraceRequest

_request_adapter: TypeAdapter[TraceRequest] = TypeAdapter(TraceRequest)


class TraceFormatError(ValueError):
    pass


@dataclass(frozen=True)
class Trace:
    header: TraceHeader
    requests: list[TraceRequest]
    sha256: str


def request_lines(requests: list[TraceRequest]) -> list[str]:
    return [_request_adapter.dump_json(r).decode() for r in requests]


def finalize(header: TraceHeader, requests: list[TraceRequest]) -> TraceHeader:
    """Set n_requests and, for format v3, the content-addressed trace_id."""
    update: dict[str, object] = {"n_requests": len(requests)}
    if header.format_version >= 3:
        update["trace_id"] = content_trace_id(request_lines(requests))
    return header.model_copy(update=update)


def dumps(header: TraceHeader, requests: list[TraceRequest]) -> str:
    header = finalize(header, requests)
    lines = [header.model_dump_json(), *request_lines(requests)]
    return "\n".join(lines) + "\n"


def write_trace(path: Path, header: TraceHeader, requests: list[TraceRequest]) -> str:
    """Write a trace and return the file's SHA-256."""
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
    if header.format_version not in SUPPORTED_FORMAT_VERSIONS:
        raise TraceFormatError(f"unsupported trace format version {header.format_version}")
    body = [line for line in lines[1:] if line.strip()]
    requests = [_request_adapter.validate_json(line) for line in body]
    if header.format_version >= 3 and header.trace_id != content_trace_id(body):
        raise TraceFormatError("trace_id doesn't match the request lines (edited or corrupt)")
    if len(requests) != header.n_requests:
        raise TraceFormatError(f"header says {header.n_requests} requests, found {len(requests)}")
    if any(b.send_at_s < a.send_at_s for a, b in zip(requests, requests[1:], strict=False)):
        raise TraceFormatError("requests must be sorted by send_at_s")
    return Trace(header=header, requests=requests, sha256=hashlib.sha256(raw).hexdigest())
