"""Trace format (decision 4B: pre-generated traces).

A trace is a JSONL file. Line 1 is a TraceHeader; every following line is one
request, sorted by send time. Requests reference corpus files by (repo, path) and
character offsets rather than embedding the text, so traces stay small; the header
records the corpus SHA-256 so a replay against a different corpus fails loudly.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

TRACE_FORMAT_VERSION = 3
SUPPORTED_FORMAT_VERSIONS = (1, 2, 3)


class FileRef(BaseModel):
    repo: str
    path: str


class CompletionRequest(BaseModel):
    """Inline completion: the editor sends the code before (and after) the cursor."""

    workload: Literal["completion"] = "completion"
    req_id: str
    send_at_s: float = Field(ge=0)
    file: FileRef
    cursor: int = Field(ge=0, description="Character offset of the cursor in the file")
    prefix_chars: int = Field(gt=0)
    suffix_chars: int = Field(ge=0)
    context_files: list[FileRef] = Field(default_factory=list)
    max_tokens: int = Field(gt=0)
    # Sizes the traffic model asked for, in tokens (format v2).
    target_prompt_tokens: int | None = Field(default=None, gt=0)
    target_output_tokens: int | None = Field(default=None, gt=0)
    # Format v3 (ADR-0005 D5): the exact length, in characters, of the prompt the gateway
    # will build for this request, and whether the target is structurally below the
    # smallest prompt Relay's template can produce (kept as generated, never resampled).
    expected_prompt_chars: int | None = Field(default=None, gt=0)
    below_template_minimum: bool = False


class AgentRequest(BaseModel):
    """Agent chat: a question about a file, with tools available."""

    workload: Literal["agent"] = "agent"
    req_id: str
    send_at_s: float = Field(ge=0)
    file: FileRef
    question_id: int = Field(ge=0)
    context_chars: int = Field(gt=0)
    max_tokens: int = Field(gt=0)


class IndexingRequest(BaseModel):
    """Repo indexing job: a batch of file chunks to embed, sent via SQS."""

    workload: Literal["indexing"] = "indexing"
    req_id: str
    send_at_s: float = Field(ge=0)
    files: list[FileRef] = Field(min_length=1)
    chunk_chars: int = Field(gt=0)


TraceRequest = Annotated[
    CompletionRequest | AgentRequest | IndexingRequest, Field(discriminator="workload")
]


class TraceHeader(BaseModel):
    format_version: int = TRACE_FORMAT_VERSION
    trace_id: str
    seed: int
    duration_s: float
    n_requests: int
    corpus_sha256: str
    generator: str
    params: dict[str, object]
    # Format v2: traffic-model traces (ADR-0004).
    kind: str = "constant"  # constant | day | window
    start_utc_s: float = 0.0  # seconds after midnight UTC that send_at_s = 0 corresponds to
    scale: float | None = None  # fraction of Relay's full traffic this trace represents
    traffic_model_sha256: str | None = None
    # Format v3: identity (ADR-0005 D7, relay.traces.identity). In v3, trace_id is the
    # SHA-256 of the request lines; in v1/v2 it was derived from the spec (legacy).
    spec_id: str | None = None
    generator_sha256: str | None = None
