"""A tiny fake OpenAI-compatible inference server for tests.

Streams a fixed number of chunks with a set time to first token and inter-token
delay, serves embeddings, and exposes vLLM-named Prometheus metrics, so the
gateway, worker and load generator can be tested without containers or a GPU.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from prometheus_client import CollectorRegistry, Counter, Histogram, make_asgi_app

TTFT_BUCKETS = (0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0)


@dataclass
class FakeConfig:
    ttft_s: float = 0.02
    itl_s: float = 0.002
    chunks: int = 5
    fail_status: int | None = None  # respond with this status to every request
    embed_delay_s: float = 0.0
    embed_dims: int = 8


def create_fake_inference(config: FakeConfig | None = None) -> FastAPI:
    cfg = config or FakeConfig()
    registry = CollectorRegistry()
    ttft = Histogram(
        "vllm:time_to_first_token_seconds", "ttft", buckets=TTFT_BUCKETS, registry=registry
    )
    success = Counter("vllm:request_success", "ok", registry=registry)
    app = FastAPI()
    app.mount("/metrics", make_asgi_app(registry=registry))
    app.state.requests = []

    async def stream(chat: bool) -> AsyncIterator[str]:
        start = time.perf_counter()
        await asyncio.sleep(cfg.ttft_s)
        for i in range(cfg.chunks):
            if i == 0:
                ttft.observe(time.perf_counter() - start)
            else:
                await asyncio.sleep(cfg.itl_s)
            choice: dict[str, Any] = (
                {"index": 0, "delta": {"content": f"tok{i} "}}
                if chat
                else {"index": 0, "text": f"tok{i} "}
            )
            yield f"data: {json.dumps({'choices': [choice]})}\n\n"
        yield "data: [DONE]\n\n"
        success.inc()

    async def handle(request: Request, chat: bool) -> Any:
        app.state.requests.append(await request.json())
        if cfg.fail_status:
            return JSONResponse({"error": "fake failure"}, status_code=cfg.fail_status)
        return StreamingResponse(stream(chat), media_type="text/event-stream")

    @app.post("/v1/completions")
    async def completions(request: Request) -> Any:
        return await handle(request, chat=False)

    @app.post("/v1/chat/completions")
    async def chat(request: Request) -> Any:
        return await handle(request, chat=True)

    @app.post("/v1/embeddings")
    async def embeddings(request: Request) -> Any:
        body = await request.json()
        if cfg.fail_status:
            return JSONResponse({"error": "fake failure"}, status_code=cfg.fail_status)
        await asyncio.sleep(cfg.embed_delay_s)
        inputs = body["input"] if isinstance(body["input"], list) else [body["input"]]
        return {
            "data": [{"index": i, "embedding": [0.1] * cfg.embed_dims} for i in range(len(inputs))]
        }

    return app
