"""Editing-session traces for RLY-4 (prefix caching).

Inline completions arrive in sessions: a user types in one file, pauses, gets a
suggestion, types a little more, pauses again. Successive requests in a session send
the same file from its start up to a cursor that has moved forward a few dozen
characters. That repeated context is what a prefix cache can reuse.

Two variants share one arrival schedule and one cursor schedule, so they differ only
in whether context repeats:

  shared       each session stays in one file (the RLY-4 workload)
  independent  every request uses a different file (the negative control: there is
               no repeated file context, so only the system prompt can be reused)

Requests are ordered session by session. That models one user's session landing on one
server whose cache holds that session. It doesn't model many users competing for cache
space; see the RLY-4 write-up for what that leaves open.

Usage:
  relay-trace-sessions --sessions 12 --per-session 8 --rate 0.5 --seed 4 \
      --out traces/rly4-shared.jsonl
  relay-trace-sessions ... --independent --out traces/rly4-independent.jsonl
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from relay.config import get_settings
from relay.corpus.manifest import load_lock
from relay.corpus.store import Corpus, CorpusFile, load_corpus
from relay.traces import identity
from relay.traces.io import write_trace
from relay.traces.schema import CompletionRequest, FileRef, TraceHeader, TraceRequest

GENERATOR = "sessions-v1"


@dataclass(frozen=True)
class SessionParams:
    n_sessions: int
    per_session: int
    rate_rps: float  # Poisson arrivals across the whole trace
    seed: int
    shared: bool = True
    first_cursor_chars: int = 2_000  # where the first request's cursor sits
    step_chars: tuple[int, int] = (80, 240)  # characters typed between two requests
    max_tokens: int = 16  # fixed, so decode work is identical across variants

    def validate(self) -> None:
        if self.n_sessions <= 0 or self.per_session <= 0 or self.rate_rps <= 0:
            raise ValueError("sessions, requests per session and rate must be positive")
        lo, hi = self.step_chars
        if not 0 < lo <= hi:
            raise ValueError("step_chars must be 0 < lo <= hi")

    @property
    def max_cursor(self) -> int:
        return self.first_cursor_chars + (self.per_session - 1) * self.step_chars[1]


def _eligible(corpus: Corpus, min_chars: int) -> list[CorpusFile]:
    files = sorted(
        (f for f in corpus.files if len(f.text) >= min_chars), key=lambda f: (f.repo, f.path)
    )
    if not files:
        raise ValueError(f"no corpus file has at least {min_chars} characters")
    return files


def generate_sessions(corpus: Corpus, params: SessionParams) -> list[TraceRequest]:
    params.validate()
    n_total = params.n_sessions * params.per_session
    # Two independent random streams: the schedule (arrivals, cursor steps) and the file
    # choice. The schedule stream never depends on `shared`, so the shared and independent
    # traces have identical send times and cursors and differ only in which file each
    # request uses.
    schedule_rng = np.random.default_rng([params.seed, 0])
    file_rng = np.random.default_rng([params.seed, 1])
    gaps = schedule_rng.exponential(1.0 / params.rate_rps, size=n_total)
    send_at = np.cumsum(gaps)
    lo, hi = params.step_chars
    steps = schedule_rng.integers(lo, hi + 1, size=(params.n_sessions, params.per_session - 1))

    files = _eligible(corpus, params.max_cursor)
    n_files = params.n_sessions if params.shared else n_total
    if n_files > len(files):
        raise ValueError(f"need {n_files} distinct files of >= {params.max_cursor} chars")
    chosen = [files[int(i)] for i in file_rng.choice(len(files), size=n_files, replace=False)]

    requests: list[TraceRequest] = []
    for s in range(params.n_sessions):
        cursor = params.first_cursor_chars
        for k in range(params.per_session):
            if k:
                cursor += int(steps[s, k - 1])
            i = s * params.per_session + k
            f = chosen[s] if params.shared else chosen[i]
            requests.append(
                CompletionRequest(
                    req_id=f"s{s:03d}-{k:02d}",
                    send_at_s=round(float(send_at[i]), 6),
                    file=FileRef(repo=f.repo, path=f.path),
                    cursor=cursor,
                    prefix_chars=cursor,  # the editor sends the file from its start
                    suffix_chars=0,
                    context_files=[],
                    max_tokens=params.max_tokens,
                )
            )
    return requests


def build_header(corpus: Corpus, params: SessionParams, n_requests: int) -> TraceHeader:
    p = asdict(params)
    spec = {"generator": GENERATOR, **p, "corpus_sha256": corpus.sha256}
    return TraceHeader(
        trace_id="",
        seed=params.seed,
        duration_s=0.0,  # set from the last send time below
        n_requests=n_requests,
        corpus_sha256=corpus.sha256,
        generator=GENERATOR,
        params=p,
        kind="sessions",
        spec_id=identity.spec_id(spec),
        generator_sha256=identity.generator_sha256(),
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--sessions", type=int, required=True)
    parser.add_argument("--per-session", type=int, required=True)
    parser.add_argument("--rate", type=float, required=True, help="mean requests/second")
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--max-tokens", type=int, default=16)
    parser.add_argument("--first-cursor", type=int, default=2_000, help="chars")
    parser.add_argument("--independent", action="store_true", help="negative control")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    settings = get_settings()
    corpus = load_corpus(load_lock(settings.corpus_lock), settings.corpus_dir)
    params = SessionParams(
        n_sessions=args.sessions,
        per_session=args.per_session,
        rate_rps=args.rate,
        seed=args.seed,
        shared=not args.independent,
        max_tokens=args.max_tokens,
        first_cursor_chars=args.first_cursor,
    )
    requests = generate_sessions(corpus, params)
    header = build_header(corpus, params, len(requests))
    header = header.model_copy(update={"duration_s": requests[-1].send_at_s})
    digest = write_trace(args.out, header, requests)
    print(f"wrote {len(requests)} requests to {args.out} (file sha256 {digest})")


if __name__ == "__main__":
    main()
