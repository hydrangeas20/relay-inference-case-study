"""Relay's API gateway (decision 1B: Relay-shaped API; decision 2A: stream end to end).

Endpoints:
  POST /v1/complete  inline completion; builds a prompt from Relay's template
  POST /v1/agent     agent chat with tools
  GET  /healthz
  GET  /metrics      Prometheus

Both generation endpoints stream Server-Sent Events straight through from the
inference server, so client-side timings include the gateway, as users feel it.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, make_asgi_app
from pydantic import BaseModel, Field

from relay.config import Settings, get_settings
from relay.gateway import templates
from relay.sse import chunk_content

LATENCY_BUCKETS = (
    0.01, 0.025, 0.05, 0.075, 0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5,
    0.75, 1.0, 1.5, 2.0, 3.0, 5.0, 10.0, 30.0, 60.0,
)  # fmt: skip


class ContextFile(BaseModel):
    path: str
    content: str


class CompleteBody(BaseModel):
    request_id: str
    repo: str
    file_path: str
    language: str
    prefix: str
    suffix: str = ""  # accepted from editors; unused until the model's FIM format is chosen
    context_files: list[ContextFile] = Field(default_factory=list)
    max_tokens: int = Field(gt=0, le=4096)


class AgentBody(BaseModel):
    request_id: str
    repo: str
    file_path: str
    language: str
    file_content: str
    question: str
    max_tokens: int = Field(gt=0, le=4096)


@dataclass
class GatewayMetrics:
    registry: CollectorRegistry
    requests: Counter
    duration: Histogram
    upstream_ttft: Histogram
    in_flight: Gauge

    @classmethod
    def create(cls) -> GatewayMetrics:
        registry = CollectorRegistry()
        return cls(
            registry=registry,
            requests=Counter(
                "relay_gateway_requests",
                "Requests handled by the gateway",
                ["workload", "status"],
                registry=registry,
            ),
            duration=Histogram(
                "relay_gateway_request_duration_seconds",
                "Gateway request duration, from receipt to last byte streamed",
                ["workload"],
                buckets=LATENCY_BUCKETS,
                registry=registry,
            ),
            upstream_ttft=Histogram(
                "relay_gateway_upstream_ttft_seconds",
                "Time from the gateway sending upstream to the first content chunk",
                ["workload"],
                buckets=LATENCY_BUCKETS,
                registry=registry,
            ),
            in_flight=Gauge(
                "relay_gateway_in_flight",
                "Requests currently streaming",
                ["workload"],
                registry=registry,
            ),
        )


def create_app(
    settings: Settings | None = None, transport: httpx.AsyncBaseTransport | None = None
) -> FastAPI:
    settings = settings or get_settings()
    metrics = GatewayMetrics.create()
    client = httpx.AsyncClient(
        base_url=settings.inference_base_url,
        timeout=httpx.Timeout(settings.inference_timeout_s, connect=5.0),
        limits=httpx.Limits(max_connections=None, max_keepalive_connections=200),
        transport=transport,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield
        await client.aclose()

    app = FastAPI(title="Relay gateway", lifespan=lifespan)
    app.mount("/metrics", make_asgi_app(registry=metrics.registry))
    app.state.metrics = metrics

    async def stream_upstream(path: str, body: dict[str, Any], workload: str) -> StreamingResponse:
        received = time.perf_counter()
        metrics.in_flight.labels(workload).inc()
        try:
            upstream = await client.send(client.build_request("POST", path, json=body), stream=True)
        except httpx.HTTPError as exc:
            metrics.in_flight.labels(workload).dec()
            metrics.requests.labels(workload, "upstream_unreachable").inc()
            raise HTTPException(502, f"inference server unreachable: {exc!r}") from exc
        if upstream.status_code != 200:
            detail = (await upstream.aread()).decode(errors="replace")[:500]
            await upstream.aclose()
            metrics.in_flight.labels(workload).dec()
            metrics.requests.labels(workload, f"upstream_{upstream.status_code}").inc()
            raise HTTPException(502, f"inference server returned {upstream.status_code}: {detail}")

        async def relay_stream() -> AsyncIterator[str]:
            status = "ok"
            first_chunk_seen = False
            try:
                async for line in upstream.aiter_lines():
                    if not first_chunk_seen and chunk_content(line):
                        first_chunk_seen = True
                        metrics.upstream_ttft.labels(workload).observe(
                            time.perf_counter() - received
                        )
                    yield line + "\n"
            except httpx.HTTPError:
                status = "upstream_stream_error"
                raise
            except asyncio.CancelledError:
                status = "client_disconnected"
                raise
            finally:
                await upstream.aclose()
                metrics.in_flight.labels(workload).dec()
                metrics.duration.labels(workload).observe(time.perf_counter() - received)
                metrics.requests.labels(workload, status).inc()

        return StreamingResponse(relay_stream(), media_type="text/event-stream")

    @app.post("/v1/complete")
    async def complete(body: CompleteBody) -> StreamingResponse:
        prompt = templates.completion_prompt(
            request_id=body.request_id,
            repo=body.repo,
            file_path=body.file_path,
            language=body.language,
            prefix=body.prefix,
            context_files=[(c.path, c.content) for c in body.context_files],
        )
        upstream_body = {
            "model": settings.completion_model,
            "prompt": prompt,
            "max_tokens": body.max_tokens,
            "temperature": 0,
            "stream": True,
        }
        return await stream_upstream("/completions", upstream_body, "completion")

    @app.post("/v1/agent")
    async def agent(body: AgentBody) -> StreamingResponse:
        messages = templates.agent_messages(
            request_id=body.request_id,
            repo=body.repo,
            file_path=body.file_path,
            language=body.language,
            file_content=body.file_content,
            question=body.question,
        )
        upstream_body = {
            "model": settings.completion_model,
            "messages": messages,
            "tools": templates.AGENT_TOOLS,
            "max_tokens": body.max_tokens,
            "temperature": 0,
            "stream": True,
        }
        return await stream_upstream("/chat/completions", upstream_body, "agent")

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


def main() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(create_app(settings), host="0.0.0.0", port=settings.gateway_port)


if __name__ == "__main__":
    main()
