"""Repo-indexing worker (decision 6B: bounded concurrency from the start).

Pulls indexing jobs from SQS, embeds their chunks via the inference server's
/embeddings endpoint, and records each job in DynamoDB. At most
WORKER_MAX_IN_FLIGHT jobs run at once: the worker only receives as many messages
as it has free slots, so it never holds messages it can't start (which would let
their visibility timeout expire while they wait).
"""

from __future__ import annotations

import asyncio
import json
import logging
import signal
import time
from dataclasses import dataclass
from typing import Any

import httpx
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, start_http_server

from relay import aws
from relay.config import Settings, get_settings

log = logging.getLogger("relay.worker")

MAX_RECEIVES = 5  # after this many failed attempts a job is recorded as failed and dropped
JOB_BUCKETS = (0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60, 120, 300, 600, 1800, 3600)


@dataclass
class WorkerMetrics:
    registry: CollectorRegistry
    jobs: Counter
    chunks: Counter
    job_duration: Histogram
    queue_lag: Histogram
    in_flight: Gauge

    @classmethod
    def create(cls) -> WorkerMetrics:
        r = CollectorRegistry()
        return cls(
            registry=r,
            jobs=Counter("relay_worker_jobs", "Indexing jobs processed", ["status"], registry=r),
            chunks=Counter("relay_worker_chunks", "Chunks embedded", registry=r),
            job_duration=Histogram(
                "relay_worker_job_duration_seconds",
                "Time to embed and record one job",
                buckets=JOB_BUCKETS,
                registry=r,
            ),
            queue_lag=Histogram(
                "relay_worker_queue_lag_seconds",
                "Time from enqueue to the worker starting the job",
                buckets=JOB_BUCKETS,
                registry=r,
            ),
            in_flight=Gauge("relay_worker_in_flight", "Jobs currently running", registry=r),
        )


class IndexWorker:
    def __init__(
        self,
        settings: Settings,
        sqs: Any,
        dynamodb: Any,
        http: httpx.AsyncClient,
        metrics: WorkerMetrics | None = None,
    ) -> None:
        if settings.worker_max_in_flight < 1:
            raise ValueError("WORKER_MAX_IN_FLIGHT must be at least 1")
        self.settings = settings
        self.sqs = sqs
        self.dynamodb = dynamodb
        self.http = http
        self.metrics = metrics or WorkerMetrics.create()
        self.queue_url = aws.queue_url(sqs, settings)
        self._in_flight: set[asyncio.Task[None]] = set()
        self.max_observed_in_flight = 0

    async def run(self, stop: asyncio.Event) -> None:
        limit = self.settings.worker_max_in_flight
        while not stop.is_set():
            free = limit - len(self._in_flight)
            if free <= 0:
                await asyncio.wait(self._in_flight, return_when=asyncio.FIRST_COMPLETED)
                continue
            resp = await asyncio.to_thread(
                self.sqs.receive_message,
                QueueUrl=self.queue_url,
                MaxNumberOfMessages=min(10, free),
                WaitTimeSeconds=self.settings.worker_poll_wait_s,
                MessageSystemAttributeNames=["SentTimestamp", "ApproximateReceiveCount"],
            )
            for message in resp.get("Messages", []):
                task = asyncio.create_task(self.handle(message))
                self._in_flight.add(task)
                task.add_done_callback(self._in_flight.discard)
                self.max_observed_in_flight = max(self.max_observed_in_flight, len(self._in_flight))
        if self._in_flight:
            await asyncio.wait(self._in_flight)

    async def handle(self, message: dict[str, Any]) -> None:
        started = time.time()
        attrs = message.get("Attributes", {})
        enqueued = int(attrs.get("SentTimestamp", started * 1000)) / 1000
        receives = int(attrs.get("ApproximateReceiveCount", 1))
        self.metrics.in_flight.inc()
        self.metrics.queue_lag.observe(max(0.0, started - enqueued))
        job_id = message["MessageId"]
        try:
            job = json.loads(message["Body"])
            job_id = job["job_id"]
            resp = await self.http.post(
                "/embeddings",
                json={"model": self.settings.embedding_model, "input": job["chunks"]},
            )
            resp.raise_for_status()
            data = resp.json()["data"]
            if len(data) != len(job["chunks"]):
                raise ValueError(f"expected {len(job['chunks'])} embeddings, got {len(data)}")
            dims = len(data[0]["embedding"]) if data else 0
            await self._record(job_id, job["repo"], len(data), dims, enqueued, started, "ok")
            await self._delete(message)
            self.metrics.chunks.inc(len(data))
            self.metrics.jobs.labels("ok").inc()
        except Exception:
            log.exception("job %s failed (attempt %d)", job_id, receives)
            if receives >= MAX_RECEIVES:
                await self._record(job_id, "", 0, 0, enqueued, started, "failed")
                await self._delete(message)
                self.metrics.jobs.labels("failed").inc()
            else:
                # Leave the message; it becomes visible again after the visibility timeout.
                self.metrics.jobs.labels("retry").inc()
        finally:
            self.metrics.in_flight.dec()
            self.metrics.job_duration.observe(time.time() - started)

    async def _record(
        self,
        job_id: str,
        repo: str,
        n_chunks: int,
        dims: int,
        enqueued: float,
        started: float,
        status: str,
    ) -> None:
        item = {
            "job_id": {"S": job_id},
            "repo": {"S": repo},
            "status": {"S": status},
            "n_chunks": {"N": str(n_chunks)},
            "embedding_dims": {"N": str(dims)},
            "enqueued_at": {"N": f"{enqueued:.3f}"},
            "started_at": {"N": f"{started:.3f}"},
            "completed_at": {"N": f"{time.time():.3f}"},
        }
        await asyncio.to_thread(
            self.dynamodb.put_item, TableName=self.settings.results_table_name, Item=item
        )

    async def _delete(self, message: dict[str, Any]) -> None:
        await asyncio.to_thread(
            self.sqs.delete_message,
            QueueUrl=self.queue_url,
            ReceiptHandle=message["ReceiptHandle"],
        )


async def _main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    metrics = WorkerMetrics.create()
    start_http_server(settings.worker_metrics_port, registry=metrics.registry)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    async with httpx.AsyncClient(
        base_url=settings.inference_base_url, timeout=settings.inference_timeout_s
    ) as http:
        worker = IndexWorker(
            settings, aws.client("sqs", settings), aws.client("dynamodb", settings), http, metrics
        )
        log.info("worker started, max in flight %d", settings.worker_max_in_flight)
        await worker.run(stop)


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
