import json
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from prometheus_client import generate_latest

from relay.config import Settings
from relay.gateway import templates
from relay.gateway.app import create_app
from relay.sse import chunk_content
from tests.fakes import FakeConfig, create_fake_inference

COMPLETE = {
    "request_id": "r0000001",
    "repo": "demo",
    "file_path": "src/app.py",
    "language": "python",
    "prefix": "def add(a, b):\n    ",
    "context_files": [{"path": "src/util.py", "content": "def helper(): ..."}],
    "max_tokens": 16,
}
AGENT = {
    "request_id": "r0000002",
    "repo": "demo",
    "file_path": "src/app.py",
    "language": "python",
    "file_content": "def add(a, b):\n    return a + b\n",
    "question": "What does this file do?",
    "max_tokens": 64,
}


def _gateway(fake: FastAPI) -> tuple[FastAPI, httpx.AsyncClient]:
    settings = Settings(_env_file=None, inference_base_url="http://inference/v1")  # type: ignore[call-arg]
    app = create_app(settings, transport=httpx.ASGITransport(app=fake))
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://gw")
    return app, client


def _metric(app: FastAPI, name: str, labels: dict[str, str]) -> float:
    for family in app.state.metrics.registry.collect():
        for s in family.samples:
            if s.name == name and all(s.labels.get(k) == v for k, v in labels.items()):
                return float(s.value)
    return 0.0


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ('data: {"choices":[{"text":"abc"}]}', "abc"),
        ('data: {"choices":[{"delta":{"content":"hi"}}]}', "hi"),
        (
            'data: {"choices":[{"delta":{"tool_calls":[{"function":{"name":"read_file"}}]}}]}',
            "read_file",
        ),
        ('data: {"choices":[{"delta":{"role":"assistant"}}]}', None),
        ("data: [DONE]", None),
        ("", None),
        ("event: ping", None),
        ("data: not json", None),
    ],
)
def test_chunk_content(line: str, expected: str | None) -> None:
    assert chunk_content(line) == expected


def test_completion_prompt_starts_with_per_request_header() -> None:
    # Documents Relay's template as found; RLY-4 is about exactly this header.
    now = datetime(2026, 1, 1, tzinfo=UTC)
    prompt = templates.completion_prompt(
        request_id="r1",
        repo="demo",
        file_path="a.py",
        language="python",
        prefix="x = ",
        context_files=[("b.py", "y = 1")],
        now=now,
    )
    assert prompt.startswith("[relay request_id=r1 ts=2026-01-01T00:00:00.000+00:00]")
    assert "--- b.py ---\ny = 1" in prompt
    assert prompt.endswith("--- a.py (python) ---\nx = ")


async def test_completion_streams_through_and_builds_prompt() -> None:
    fake = create_fake_inference(FakeConfig(chunks=4))
    app, client = _gateway(fake)
    async with client:
        resp = await client.post("/v1/complete", json=COMPLETE)
    assert resp.status_code == 200
    chunks = [c for line in resp.text.splitlines() if (c := chunk_content(line))]
    assert chunks == ["tok0 ", "tok1 ", "tok2 ", "tok3 "]
    upstream: dict[str, Any] = fake.state.requests[0]
    assert upstream["stream"] is True
    assert upstream["prompt"].startswith("[relay request_id=r0000001")
    assert upstream["prompt"].endswith(COMPLETE["prefix"])
    assert (
        _metric(app, "relay_gateway_requests_total", {"workload": "completion", "status": "ok"})
        == 1
    )
    assert (
        _metric(app, "relay_gateway_upstream_ttft_seconds_count", {"workload": "completion"}) == 1
    )


async def test_agent_sends_tools_and_messages() -> None:
    fake = create_fake_inference()
    app, client = _gateway(fake)
    async with client:
        resp = await client.post("/v1/agent", json=AGENT)
    assert resp.status_code == 200
    upstream = fake.state.requests[0]
    assert [t["function"]["name"] for t in upstream["tools"]] == [
        "search_repo",
        "read_file",
        "run_tests",
    ]
    assert upstream["messages"][0]["role"] == "system"
    assert AGENT["question"] in upstream["messages"][1]["content"]


async def test_upstream_error_becomes_502_and_is_counted() -> None:
    app, client = _gateway(create_fake_inference(FakeConfig(fail_status=503)))
    async with client:
        resp = await client.post("/v1/complete", json=COMPLETE)
    assert resp.status_code == 502
    assert "503" in json.loads(resp.text)["detail"]
    assert (
        _metric(
            app,
            "relay_gateway_requests_total",
            {"workload": "completion", "status": "upstream_503"},
        )
        == 1
    )
    assert _metric(app, "relay_gateway_in_flight", {"workload": "completion"}) == 0


async def test_validation_rejects_bad_body() -> None:
    _, client = _gateway(create_fake_inference())
    async with client:
        resp = await client.post("/v1/complete", json={**COMPLETE, "max_tokens": 0})
    assert resp.status_code == 422


async def test_metrics_endpoint_exposes_gateway_metrics() -> None:
    app, client = _gateway(create_fake_inference())
    async with client:
        await client.post("/v1/complete", json=COMPLETE)
        resp = await client.get("/metrics/")
    assert resp.status_code == 200
    assert "relay_gateway_upstream_ttft_seconds_bucket" in resp.text
    assert generate_latest(app.state.metrics.registry).decode() != ""
