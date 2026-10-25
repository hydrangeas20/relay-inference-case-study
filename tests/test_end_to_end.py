"""Full path over real sockets: load generator -> gateway -> fake inference server.

No containers or GPU: the gateway and a fake OpenAI-compatible server run in
background threads on local ports. Checks that a replay produces a valid run
whose client, gateway and server TTFT measurements reconcile.
"""

from __future__ import annotations

import hashlib
import json
import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from fastapi import FastAPI
from prometheus_client import Histogram

from relay.config import Settings
from relay.corpus.manifest import CorpusLock, LockedFile, write_lock
from relay.corpus.store import Corpus
from relay.gateway.app import create_app
from relay.loadgen.runner import run_trace
from relay.traces.generate import GeneratorParams, build_header, generate
from relay.traces.io import read_trace, write_trace
from tests.fakes import FakeConfig, create_fake_inference


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture
def serve() -> Iterator[object]:
    servers: list[uvicorn.Server] = []

    def start(app: FastAPI) -> str:
        port = _free_port()
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
        threading.Thread(target=server.run, daemon=True).start()
        for _ in range(100):
            if server.started:
                break
            time.sleep(0.05)
        servers.append(server)
        return f"http://127.0.0.1:{port}"

    yield start
    for server in servers:
        server.should_exit = True


class _RecordingHistogram:
    """Stands in for a labelled histogram: observes as usual and keeps every value."""

    def __init__(self, hist: Histogram) -> None:
        self.hist = hist
        self.values: list[float] = []

    def labels(self, *labels: str) -> Any:
        child, values = self.hist.labels(*labels), self.values

        class _Child:
            def observe(self, value: float) -> None:
                values.append(value)
                child.observe(value)

        return _Child()


def _write_corpus(corpus: Corpus, root: Path) -> tuple[Path, Path, str]:
    files = []
    for f in corpus.files:
        path = root / "corpus" / f.repo / f.path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f.text)
        files.append(
            LockedFile(
                repo=f.repo,
                language=f.language,
                path=f.path,
                sha256=hashlib.sha256(f.text.encode()).hexdigest(),
                bytes=len(f.text.encode()),
            )
        )
    lock = CorpusLock(manifest_sha256="0" * 64, files=files)
    write_lock(lock, root / "corpus.lock.json")
    return root / "corpus.lock.json", root / "corpus", lock.sha256


async def test_replay_is_valid_and_reconciles(
    serve: object, small_corpus: Corpus, tmp_path: Path
) -> None:
    start = serve  # type: ignore[assignment]
    lock_path, corpus_dir, corpus_sha = _write_corpus(small_corpus, tmp_path)
    fake_url = start(create_fake_inference(FakeConfig(ttft_s=0.03, itl_s=0.002, chunks=4)))  # type: ignore[operator]
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        inference_base_url=f"{fake_url}/v1",
        inference_metrics_url=f"{fake_url}/metrics/",
        corpus_lock=lock_path,
        corpus_dir=corpus_dir,
    )
    gateway_app = create_app(settings)
    gateway_ttft = _RecordingHistogram(gateway_app.state.metrics.upstream_ttft)
    gateway_app.state.metrics.upstream_ttft = gateway_ttft
    gateway_url = start(gateway_app)  # type: ignore[operator]
    settings = settings.model_copy(update={"gateway_url": gateway_url})

    corpus = Corpus(small_corpus.files, corpus_sha)
    params = GeneratorParams(
        duration_s=3, rate_rps=10, seed=11, mix={"completion": 0.8, "agent": 0.2}
    )
    reqs = generate(corpus, params)
    trace_path = tmp_path / "trace.jsonl"
    write_trace(trace_path, build_header(corpus, params, len(reqs)), reqs)

    summary = await run_trace(trace_path, tmp_path / "results", settings)

    # This is a functional test: the replay must work, and the self-check must run and
    # report. Whether this host kept send lag under the 10 ms measurement bar, or kept the
    # generator's CPU unsaturated, depends on the machine, not the code. Those gates are
    # tested deterministically in test_stats_and_selfcheck.py and enforced on every real
    # run by the load generator. Asserting them here made this test fail under shared-runner
    # CPU contention (PR #3 review: 3/23 local failures under load, all send lag).
    check = summary["self_check"]
    assert check["send_lag_s"]["p99"] is not None
    assert check["cpu_pct"]["p95"] is not None
    host_dependent = ("send lag", "generator CPU")
    functional_failures = [r for r in check["reasons"] if not r.startswith(host_dependent)]
    assert functional_failures == [], functional_failures
    sent = sum(w["sent"] for w in summary["workloads"].values())
    ok = sum(w["ok"] for w in summary["workloads"].values())
    assert sent == ok == len(reqs)
    assert summary["workloads"]["completion"]["ttft_s"]["p50"] >= 0.03
    recon = summary["reconciliation"]
    assert recon["status"] == "consistent", recon["problems"]
    assert [layer["name"] for layer in recon["layers"]] == ["server", "gateway", "client"]
    raw = list((tmp_path / "results" / "raw").glob("*.jsonl"))
    assert len(raw) == 1
    assert len(raw[0].read_text().splitlines()) == len(reqs)
    first = json.loads(raw[0].read_text().splitlines()[0])
    assert first["status"] == "ok"
    assert first["prompt_chars"] > 0  # the gateway's built-size header was recorded
    assert summary["trace"]["trace_id"] == read_trace(trace_path).header.trace_id

    # The invariant reconciliation relies on: the client's TTFT interval contains the
    # gateway's for every request, so the k-th fastest client TTFT is never below the
    # k-th fastest gateway TTFT (the gateway exposes no request IDs to match on).
    records = [json.loads(line) for line in raw[0].read_text().splitlines()]
    client = sorted(r["ttft_s"] for r in records if r["ttft_s"] is not None)
    gateway = sorted(gateway_ttft.values)
    assert len(gateway) == len(client) == len(reqs)
    gaps = [c - g for c, g in zip(client, gateway, strict=True)]
    assert min(gaps) >= 0, f"client below gateway by {-min(gaps) * 1000:.2f} ms"
