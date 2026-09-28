from pathlib import Path

import pytest

from relay import prompts
from relay.corpus.store import Corpus
from relay.traces.generate import GeneratorParams, build_header, generate
from relay.traces.io import TraceFormatError, dumps, read_trace, write_trace
from relay.traces.schema import AgentRequest, CompletionRequest, IndexingRequest


def test_same_seed_gives_identical_trace(small_corpus: Corpus) -> None:
    params = GeneratorParams(duration_s=60, rate_rps=5, seed=7)
    a, b = generate(small_corpus, params), generate(small_corpus, params)
    assert dumps(build_header(small_corpus, params, len(a)), a) == dumps(
        build_header(small_corpus, params, len(b)), b
    )


def test_different_seed_gives_different_trace(small_corpus: Corpus) -> None:
    a = generate(small_corpus, GeneratorParams(duration_s=60, rate_rps=5, seed=1))
    b = generate(small_corpus, GeneratorParams(duration_s=60, rate_rps=5, seed=2))
    assert a != b


def test_arrivals_sorted_within_duration_and_near_rate(small_corpus: Corpus) -> None:
    reqs = generate(small_corpus, GeneratorParams(duration_s=400, rate_rps=5, seed=3))
    times = [r.send_at_s for r in reqs]
    assert times == sorted(times)
    assert all(0 <= t < 400 for t in times)
    assert len(reqs) == pytest.approx(2000, rel=0.1)  # Poisson: sd ~ 45 at n=2000


def test_workload_mix_roughly_matches(small_corpus: Corpus) -> None:
    reqs = generate(small_corpus, GeneratorParams(duration_s=400, rate_rps=5, seed=4))
    share = sum(isinstance(r, CompletionRequest) for r in reqs) / len(reqs)
    assert share == pytest.approx(0.80, abs=0.04)


def test_roundtrip_and_hash(small_corpus: Corpus, tmp_path: Path) -> None:
    params = GeneratorParams(duration_s=30, rate_rps=5, seed=5)
    reqs = generate(small_corpus, params)
    path = tmp_path / "t.jsonl"
    digest = write_trace(path, build_header(small_corpus, params, len(reqs)), reqs)
    trace = read_trace(path)
    assert trace.sha256 == digest
    assert trace.requests == reqs


def test_rejects_count_mismatch(small_corpus: Corpus, tmp_path: Path) -> None:
    params = GeneratorParams(duration_s=30, rate_rps=5, seed=5)
    reqs = generate(small_corpus, params)
    path = tmp_path / "t.jsonl"
    write_trace(path, build_header(small_corpus, params, len(reqs) + 1), reqs)
    with pytest.raises(TraceFormatError):
        read_trace(path)


def test_rejects_unsorted(small_corpus: Corpus, tmp_path: Path) -> None:
    params = GeneratorParams(duration_s=30, rate_rps=5, seed=5)
    reqs = list(reversed(generate(small_corpus, params)))
    path = tmp_path / "t.jsonl"
    write_trace(path, build_header(small_corpus, params, len(reqs)), reqs)
    with pytest.raises(TraceFormatError):
        read_trace(path)


def test_payloads_resolve_from_corpus(small_corpus: Corpus) -> None:
    reqs = generate(small_corpus, GeneratorParams(duration_s=200, rate_rps=5, seed=6))
    for r in reqs:
        if isinstance(r, CompletionRequest):
            p = prompts.completion_payload(r, small_corpus)
            assert 0 < len(p["prefix"]) <= r.prefix_chars
            assert (
                p["prefix"]
                == small_corpus.get(r.file.repo, r.file.path).text[
                    max(0, r.cursor - r.prefix_chars) : r.cursor
                ]
            )
        elif isinstance(r, AgentRequest):
            p = prompts.agent_payload(r, small_corpus)
            assert p["question"] == prompts.AGENT_QUESTIONS[r.question_id]
        elif isinstance(r, IndexingRequest):
            job = prompts.indexing_job(r, small_corpus)
            assert all(len(c) <= r.chunk_chars for c in job["chunks"])
            assert {f.repo for f in r.files} == {job["repo"]}


def test_invalid_mix_rejected(small_corpus: Corpus) -> None:
    with pytest.raises(ValueError):
        generate(
            small_corpus,
            GeneratorParams(duration_s=10, rate_rps=1, seed=1, mix={"completion": 0.5}),
        )
