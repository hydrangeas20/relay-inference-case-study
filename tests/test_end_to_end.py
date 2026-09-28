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

import pytest
import uvicorn
from fastapi import FastAPI

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
    gateway_url = start(create_app(settings))  # type: ignore[operator]
    settings = settings.model_copy(update={"gateway_url": gateway_url})

    corpus = Corpus(small_corpus.files, corpus_sha)
    params = GeneratorParams(
        duration_s=3, rate_rps=10, seed=11, mix={"completion": 0.8, "agent": 0.2}
    )
    reqs = generate(corpus, params)
    trace_path = tmp_path / "trace.jsonl"
    write_trace(trace_path, build_header(corpus, params, len(reqs)), reqs)

    summary = await run_trace(trace_path, tmp_path / "results", settings)

    assert summary["valid"], summary["self_check"]["reasons"]
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
