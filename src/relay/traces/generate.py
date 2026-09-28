"""Generate a trace: Poisson arrivals at a constant rate, with a workload mix.

Usage: relay-trace --out traces/smoke.jsonl --duration 60 --rate 5 --seed 1

This is the Phase 1 generator. Phase 2 replaces the constant rate and the length
ranges below with Relay's traffic model (diurnal shape, measured length
distributions); the trace format stays the same.
"""

from __future__ import annotations

import argparse
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from relay.config import get_settings
from relay.corpus.manifest import load_lock
from relay.corpus.store import Corpus, CorpusFile, load_corpus
from relay.traces.io import write_trace
from relay.traces.schema import (
    AgentRequest,
    CompletionRequest,
    FileRef,
    IndexingRequest,
    TraceHeader,
    TraceRequest,
)

N_AGENT_QUESTIONS = 8  # must match relay.prompts.AGENT_QUESTIONS


@dataclass(frozen=True)
class GeneratorParams:
    duration_s: float
    rate_rps: float
    seed: int
    mix: dict[str, float] = field(
        default_factory=lambda: {"completion": 0.80, "agent": 0.15, "indexing": 0.05}
    )
    # Placeholder ranges until Phase 2 fits them to Relay's traffic model.
    completion_prefix_chars: tuple[int, int] = (1_000, 6_000)
    completion_suffix_chars: tuple[int, int] = (0, 1_500)
    completion_context_files: tuple[int, int] = (0, 2)
    completion_max_tokens: tuple[int, int] = (16, 64)
    agent_context_chars: tuple[int, int] = (2_000, 8_000)
    agent_max_tokens: tuple[int, int] = (128, 512)
    indexing_files: tuple[int, int] = (1, 4)
    indexing_chunk_chars: int = 1_500

    def validate(self) -> None:
        if self.duration_s <= 0 or self.rate_rps <= 0:
            raise ValueError("duration and rate must be positive")
        if abs(sum(self.mix.values()) - 1.0) > 1e-9:
            raise ValueError("workload mix must sum to 1")
        if set(self.mix) - {"completion", "agent", "indexing"}:
            raise ValueError("unknown workload in mix")


def _uniform_int(rng: np.random.Generator, bounds: tuple[int, int]) -> int:
    lo, hi = bounds
    return int(rng.integers(lo, hi + 1))


def _pick(rng: np.random.Generator, files: list[CorpusFile]) -> CorpusFile:
    return files[int(rng.integers(len(files)))]


def _ref(f: CorpusFile) -> FileRef:
    return FileRef(repo=f.repo, path=f.path)


def generate(corpus: Corpus, params: GeneratorParams) -> list[TraceRequest]:
    params.validate()
    rng = np.random.default_rng(params.seed)
    workloads = list(params.mix)
    weights = np.array([params.mix[w] for w in workloads])
    requests: list[TraceRequest] = []

    t = float(rng.exponential(1.0 / params.rate_rps))
    i = 0
    while t < params.duration_s:
        workload = workloads[int(rng.choice(len(workloads), p=weights))]
        req_id = f"r{i:07d}"
        send_at = round(t, 6)
        f = _pick(rng, corpus.files)
        if workload == "completion":
            prefix = _uniform_int(rng, params.completion_prefix_chars)
            cursor = int(rng.integers(min(prefix, len(f.text)), len(f.text) + 1))
            same_repo = [c for c in corpus.files if c.repo == f.repo and c.path != f.path]
            n_ctx = min(_uniform_int(rng, params.completion_context_files), len(same_repo))
            ctx_idx: list[int] = (
                [int(j) for j in rng.choice(len(same_repo), size=n_ctx, replace=False)]
                if n_ctx
                else []
            )
            requests.append(
                CompletionRequest(
                    req_id=req_id,
                    send_at_s=send_at,
                    file=_ref(f),
                    cursor=cursor,
                    prefix_chars=prefix,
                    suffix_chars=_uniform_int(rng, params.completion_suffix_chars),
                    context_files=[_ref(same_repo[j]) for j in ctx_idx],
                    max_tokens=_uniform_int(rng, params.completion_max_tokens),
                )
            )
        elif workload == "agent":
            requests.append(
                AgentRequest(
                    req_id=req_id,
                    send_at_s=send_at,
                    file=_ref(f),
                    question_id=int(rng.integers(N_AGENT_QUESTIONS)),
                    context_chars=_uniform_int(rng, params.agent_context_chars),
                    max_tokens=_uniform_int(rng, params.agent_max_tokens),
                )
            )
        else:
            repo_files = [c for c in corpus.files if c.repo == f.repo]
            n = min(_uniform_int(rng, params.indexing_files), len(repo_files))
            idx = rng.choice(len(repo_files), size=n, replace=False)
            requests.append(
                IndexingRequest(
                    req_id=req_id,
                    send_at_s=send_at,
                    files=[_ref(repo_files[int(j)]) for j in idx],
                    chunk_chars=params.indexing_chunk_chars,
                )
            )
        i += 1
        t += float(rng.exponential(1.0 / params.rate_rps))
    return requests


def build_header(corpus: Corpus, params: GeneratorParams, n_requests: int) -> TraceHeader:
    # The trace id is derived from the inputs so the same inputs give an identical file.
    trace_id = uuid.uuid5(
        uuid.NAMESPACE_URL, f"relay-trace:{corpus.sha256}:{sorted(asdict(params).items())}"
    ).hex[:12]
    return TraceHeader(
        trace_id=trace_id,
        seed=params.seed,
        duration_s=params.duration_s,
        n_requests=n_requests,
        corpus_sha256=corpus.sha256,
        generator="poisson-constant-v1",
        params=asdict(params),
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--duration", type=float, required=True, help="seconds")
    parser.add_argument("--rate", type=float, required=True, help="mean requests/second")
    parser.add_argument("--seed", type=int, required=True)
    args = parser.parse_args(argv)

    settings = get_settings()
    corpus = load_corpus(load_lock(settings.corpus_lock), settings.corpus_dir)
    params = GeneratorParams(duration_s=args.duration, rate_rps=args.rate, seed=args.seed)
    requests = generate(corpus, params)
    digest = write_trace(args.out, build_header(corpus, params, len(requests)), requests)
    print(f"wrote {len(requests)} requests to {args.out} (sha256 {digest})")


if __name__ == "__main__":
    main()
