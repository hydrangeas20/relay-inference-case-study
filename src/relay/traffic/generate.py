"""Generate traces from the traffic model (decision 4C: two trace types).

- day:    24 hours at real time, for the simulator (cold starts, autoscaling, RLY-7).
- window: a short slice (e.g. the morning peak) for real-GPU runs.

Both are scaled by one number: the interactive request rate at Relay's daily peak
after scaling (`peak_rps`). The trace header records the resulting scale, i.e. the
fraction of Relay's 400K daily users the trace represents.
"""

from __future__ import annotations

import bisect
import math
import uuid
from dataclasses import dataclass

import numpy as np

from relay.corpus.store import Corpus, CorpusFile
from relay.gateway import templates
from relay.prompts import CONTEXT_FILE_CHARS
from relay.traces.generate import N_AGENT_QUESTIONS
from relay.traces.schema import (
    AgentRequest,
    CompletionRequest,
    FileRef,
    IndexingRequest,
    TraceHeader,
    TraceRequest,
)
from relay.traffic.model import SECONDS_PER_DAY, TrafficModel

BIN_S = 0.1  # arrival-rate resolution; well below the 8.5 s burst correlation time
MIN_PREFIX_CHARS = 100

# Characters the gateway's completion template adds around the code (header, system
# prompt, labels), so the traffic model's prompt size covers the whole prompt.
PROMPT_OVERHEAD_CHARS = len(
    templates.completion_prompt(
        request_id="r0000000",
        repo="example-repo",
        file_path="src/example/module_name.py",
        language="python",
        prefix="",
        context_files=[],
    )
)
CONTEXT_FILE_OVERHEAD_CHARS = len("\n--- src/example/other_module.py ---\n\n")


@dataclass(frozen=True)
class TraceSpec:
    kind: str  # "day" | "window"
    peak_rps: float  # interactive requests/second at the daily peak, after scaling
    seed: int
    start_utc_s: float = 0.0
    duration_s: float = SECONDS_PER_DAY

    def validate(self) -> None:
        if self.kind not in ("day", "window"):
            raise ValueError("kind must be 'day' or 'window'")
        if self.peak_rps <= 0 or self.duration_s <= 0:
            raise ValueError("peak_rps and duration must be positive")
        if self.kind == "day" and (self.start_utc_s != 0 or self.duration_s != SECONDS_PER_DAY):
            raise ValueError("a day trace covers 00:00-24:00 UTC")
        if not 0 <= self.start_utc_s < SECONDS_PER_DAY:
            raise ValueError("start must be within the day")


class _Files:
    """Corpus files indexed for fast size-constrained picks."""

    def __init__(self, corpus: Corpus) -> None:
        self.all = corpus.files
        self.by_len = sorted(corpus.files, key=lambda f: len(f.text))
        self.lengths = [len(f.text) for f in self.by_len]
        self.by_repo: dict[str, list[CorpusFile]] = {}
        for f in corpus.files:
            self.by_repo.setdefault(f.repo, []).append(f)

    def at_least(self, rng: np.random.Generator, n_chars: int) -> CorpusFile:
        """A random file with at least n_chars, or the longest file if none is that long."""
        i = bisect.bisect_left(self.lengths, n_chars)
        if i >= len(self.by_len):
            return self.by_len[-1]
        return self.by_len[int(rng.integers(i, len(self.by_len)))]


def arrival_times(
    model: TrafficModel, spec: TraceSpec, scale: float, rng: np.random.Generator
) -> tuple[np.ndarray, np.ndarray]:
    """Interactive arrivals: (times relative to trace start, is_completion flags)."""
    n_bins = math.ceil(spec.duration_s / BIN_S)
    mid = spec.start_utc_s + (np.arange(n_bins) + 0.5) * BIN_S
    rates = model.interactive_rate_rps(mid)
    total = (rates["completion"] + rates["agent"]) * scale
    p_completion = rates["completion"] / (rates["completion"] + rates["agent"])
    expected = total * model.modulation(n_bins, BIN_S, rng) * BIN_S
    counts = rng.poisson(expected)
    bins = np.repeat(np.arange(n_bins), counts)
    times = (bins + rng.random(len(bins))) * BIN_S
    order = np.argsort(times, kind="stable")
    times, bins = times[order], bins[order]
    keep = times < spec.duration_s
    times, bins = times[keep], bins[keep]
    return times, rng.random(len(times)) < p_completion[bins]


def indexing_times(
    model: TrafficModel, spec: TraceSpec, scale: float, rng: np.random.Generator
) -> np.ndarray:
    """Indexing jobs enqueued uniformly over the nightly window, within the trace span."""
    w0 = model.indexing_window_start_utc_h * 3600
    w1 = w0 + model.indexing_window_minutes * 60
    t0, t1 = spec.start_utc_s, spec.start_utc_s + spec.duration_s
    overlap = max(0.0, min(w1, t1) - max(w0, t0))
    if overlap == 0:
        return np.empty(0)
    expected = model.indexing_jobs_per_day * scale * overlap / (w1 - w0)
    n = int(rng.poisson(expected))
    return np.sort(rng.uniform(max(w0, t0), min(w1, t1), n)) - t0


def _completion(
    model: TrafficModel, files: _Files, rng: np.random.Generator, req_id: str, t: float
) -> CompletionRequest:
    ctx_tok, gen_tok = model.completion_sizes[int(rng.integers(len(model.completion_sizes)))]
    target_chars = int(ctx_tok * model.chars_per_token)
    budget = target_chars - PROMPT_OVERHEAD_CHARS - MIN_PREFIX_CHARS
    per_ctx = CONTEXT_FILE_CHARS + CONTEXT_FILE_OVERHEAD_CHARS
    lo, hi = model.completion_context_files
    n_ctx = min(int(rng.integers(lo, hi + 1)), max(0, budget // per_ctx))
    prefix = max(MIN_PREFIX_CHARS, target_chars - PROMPT_OVERHEAD_CHARS - n_ctx * per_ctx)
    f = files.at_least(rng, prefix)
    cursor = int(rng.integers(min(prefix, len(f.text)), len(f.text) + 1))
    same_repo = [c for c in files.by_repo[f.repo] if c.path != f.path]
    n_ctx = min(n_ctx, len(same_repo))
    ctx_idx: list[int] = (
        [int(j) for j in rng.choice(len(same_repo), size=n_ctx, replace=False)] if n_ctx else []
    )
    s_lo, s_hi = model.completion_suffix_chars
    return CompletionRequest(
        req_id=req_id,
        send_at_s=t,
        file=FileRef(repo=f.repo, path=f.path),
        cursor=cursor,
        prefix_chars=prefix,
        suffix_chars=int(rng.integers(s_lo, s_hi + 1)),
        context_files=[FileRef(repo=same_repo[j].repo, path=same_repo[j].path) for j in ctx_idx],
        max_tokens=max(1, int(gen_tok)),
        target_prompt_tokens=max(1, int(ctx_tok)),
        target_output_tokens=max(1, int(gen_tok)),
    )


def _agent(
    model: TrafficModel, files: _Files, rng: np.random.Generator, req_id: str, t: float
) -> AgentRequest:
    f = files.all[int(rng.integers(len(files.all)))]
    c_lo, c_hi = model.agent_context_chars
    m_lo, m_hi = model.agent_max_tokens
    return AgentRequest(
        req_id=req_id,
        send_at_s=t,
        file=FileRef(repo=f.repo, path=f.path),
        question_id=int(rng.integers(N_AGENT_QUESTIONS)),
        context_chars=int(rng.integers(c_lo, c_hi + 1)),
        max_tokens=int(rng.integers(m_lo, m_hi + 1)),
    )


def _indexing(
    model: TrafficModel, files: _Files, rng: np.random.Generator, req_id: str, t: float
) -> IndexingRequest:
    repo = files.all[int(rng.integers(len(files.all)))].repo
    repo_files = files.by_repo[repo]
    lo, hi = model.indexing_files_per_job
    n = min(int(rng.integers(lo, hi + 1)), len(repo_files))
    idx = rng.choice(len(repo_files), size=n, replace=False)
    return IndexingRequest(
        req_id=req_id,
        send_at_s=t,
        files=[FileRef(repo=repo, path=repo_files[int(j)].path) for j in idx],
        chunk_chars=model.indexing_chunk_chars,
    )


def generate_traffic(
    model: TrafficModel, corpus: Corpus, spec: TraceSpec
) -> tuple[TraceHeader, list[TraceRequest]]:
    spec.validate()
    rng = np.random.default_rng(spec.seed)
    scale = spec.peak_rps / model.peak_interactive_rps()
    times, is_completion = arrival_times(model, spec, scale, rng)
    idx_times = indexing_times(model, spec, scale, rng)

    events = [
        (float(t), "completion" if c else "agent")
        for t, c in zip(times, is_completion, strict=True)
    ]
    events += [(float(t), "indexing") for t in idx_times]
    events.sort(key=lambda e: e[0])

    files = _Files(corpus)
    requests: list[TraceRequest] = []
    for i, (t, w) in enumerate(events):
        req_id, send_at = f"r{i:08d}", round(t, 6)
        if w == "completion":
            requests.append(_completion(model, files, rng, req_id, send_at))
        elif w == "agent":
            requests.append(_agent(model, files, rng, req_id, send_at))
        else:
            requests.append(_indexing(model, files, rng, req_id, send_at))

    params: dict[str, object] = {
        "peak_rps": spec.peak_rps,
        "users_represented": round(model.daily_active_users * scale, 1),
        "bin_s": BIN_S,
        "prompt_overhead_chars": PROMPT_OVERHEAD_CHARS,
    }
    trace_id = uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"relay-traffic:{corpus.sha256}:{model.sha256}:{spec}",
    ).hex[:12]
    header = TraceHeader(
        trace_id=trace_id,
        seed=spec.seed,
        duration_s=spec.duration_s,
        n_requests=len(requests),
        corpus_sha256=corpus.sha256,
        generator="relay-traffic-v1",
        params=params,
        kind=spec.kind,
        start_utc_s=spec.start_utc_s,
        scale=scale,
        traffic_model_sha256=model.sha256,
    )
    return header, requests
