"""Open-loop trace replay (methodology rules 4 and 5).

Usage: relay-loadgen --trace traces/smoke.jsonl [--out-dir results] [--no-reconcile]

Every request is sent at its scheduled time whether or not earlier requests have
finished. Payloads are built before the clock starts so building them can't delay
sends. Completion and agent requests stream through the gateway; indexing jobs
go onto the SQS queue.

Writes:
  results/raw/<run_id>.jsonl      one line per request (client-side timings)
  results/<run_id>.summary.json   validity self-check, percentiles, reconciliation
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import psutil

from relay import aws, prompts
from relay.config import Settings, get_settings
from relay.corpus.manifest import load_lock
from relay.corpus.store import Corpus, load_corpus
from relay.loadgen import reconcile, selfcheck
from relay.loadgen.stats import percentiles
from relay.sse import chunk_content
from relay.traces.io import Trace, read_trace
from relay.traces.schema import AgentRequest, CompletionRequest, IndexingRequest, TraceRequest

START_LEAD_S = 1.0  # time between building payloads and the first scheduled send
CPU_SAMPLE_INTERVAL_S = 0.5


@dataclass
class RequestRecord:
    req_id: str
    workload: str
    intended_send_s: float  # relative to run start
    actual_send_s: float
    status: str
    ttft_s: float | None = None  # client-side, streaming requests only
    e2e_s: float | None = None
    n_chunks: int = 0
    output_chars: int = 0
    error: str | None = None


class Replayer:
    def __init__(
        self,
        settings: Settings,
        corpus: Corpus,
        http: httpx.AsyncClient,
        sqs: Any | None,
    ) -> None:
        self.settings = settings
        self.corpus = corpus
        self.http = http
        self.sqs = sqs
        self.queue_url = aws.queue_url(sqs, settings) if sqs is not None else None
        self.cpu_samples: list[float] = []

    def build(self, req: TraceRequest) -> dict[str, Any]:
        if isinstance(req, CompletionRequest):
            return prompts.completion_payload(req, self.corpus)
        if isinstance(req, AgentRequest):
            return prompts.agent_payload(req, self.corpus)
        return prompts.indexing_job(req, self.corpus)

    async def run(self, trace: Trace) -> list[RequestRecord]:
        if self.sqs is None and any(isinstance(r, IndexingRequest) for r in trace.requests):
            raise ValueError("trace contains indexing requests but no SQS client was given")
        payloads = [self.build(r) for r in trace.requests]
        loop = asyncio.get_running_loop()
        start = loop.time() + START_LEAD_S
        sampler = asyncio.create_task(self._sample_cpu())
        tasks: list[asyncio.Task[RequestRecord]] = []
        try:
            for req, payload in zip(trace.requests, payloads, strict=True):
                delay = start + req.send_at_s - loop.time()
                if delay > 0:
                    await asyncio.sleep(delay)
                tasks.append(asyncio.create_task(self._dispatch(req, payload, start)))
            return list(await asyncio.gather(*tasks))
        finally:
            sampler.cancel()

    async def _sample_cpu(self) -> None:
        proc = psutil.Process()
        proc.cpu_percent(None)
        while True:
            await asyncio.sleep(CPU_SAMPLE_INTERVAL_S)
            self.cpu_samples.append(proc.cpu_percent(None))

    async def _dispatch(
        self, req: TraceRequest, payload: dict[str, Any], start: float
    ) -> RequestRecord:
        loop = asyncio.get_running_loop()
        sent = loop.time()
        record = RequestRecord(
            req_id=req.req_id,
            workload=req.workload,
            intended_send_s=req.send_at_s,
            actual_send_s=sent - start,
            status="ok",
        )
        try:
            if isinstance(req, IndexingRequest):
                await asyncio.to_thread(
                    self.sqs.send_message,  # type: ignore[union-attr]
                    QueueUrl=self.queue_url,
                    MessageBody=json.dumps(payload),
                )
            else:
                path = "/v1/complete" if isinstance(req, CompletionRequest) else "/v1/agent"
                await self._stream(path, payload, record, sent)
        except Exception as exc:  # recorded, never raised: one failure mustn't stop the run
            record.status = f"error:{type(exc).__name__}"
            record.error = str(exc)[:300]
        record.e2e_s = loop.time() - sent
        return record

    async def _stream(
        self, path: str, payload: dict[str, Any], record: RequestRecord, sent: float
    ) -> None:
        loop = asyncio.get_running_loop()
        async with self.http.stream("POST", path, json=payload) as resp:
            if resp.status_code != 200:
                record.status = f"http_{resp.status_code}"
                record.error = (await resp.aread()).decode(errors="replace")[:300]
                return
            async for line in resp.aiter_lines():
                content = chunk_content(line)
                if content is None:
                    continue
                if record.ttft_s is None:
                    record.ttft_s = loop.time() - sent
                record.n_chunks += 1
                record.output_chars += len(content)
        if record.ttft_s is None:
            record.status = "empty_response"


def summarize(
    run_id: str,
    settings: Settings,
    trace: Trace,
    trace_path: Path,
    records: list[RequestRecord],
    check: selfcheck.SelfCheck,
    recon: reconcile.Reconciliation | None,
) -> dict[str, Any]:
    workloads: dict[str, Any] = {}
    for workload in sorted({r.workload for r in records}):
        rs = [r for r in records if r.workload == workload]
        ok = [r for r in rs if r.status == "ok"]
        workloads[workload] = {
            "sent": len(rs),
            "ok": len(ok),
            "errors": {s: sum(r.status == s for r in rs) for s in {r.status for r in rs} - {"ok"}},
            "ttft_s": percentiles([r.ttft_s for r in ok if r.ttft_s is not None]),
            "e2e_s": percentiles([r.e2e_s for r in ok if r.e2e_s is not None]),
        }
    return {
        "schema": "phase1-provisional",  # replaced by the Phase 2 results schema
        "run_id": run_id,
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "source": settings.inference_backend,
        "trace": {
            "path": str(trace_path),
            "sha256": trace.sha256,
            "trace_id": trace.header.trace_id,
        },
        "corpus_sha256": trace.header.corpus_sha256,
        "valid": check.valid,
        "self_check": asdict(check),
        "workloads": workloads,
        "reconciliation": asdict(recon) if recon else None,
    }


async def _scrape(http: httpx.AsyncClient, url: str) -> str | None:
    try:
        resp = await http.get(url, timeout=5.0)
        resp.raise_for_status()
        return resp.text
    except httpx.HTTPError:
        return None


async def run_trace(
    trace_path: Path, out_dir: Path, settings: Settings, do_reconcile: bool = True
) -> dict[str, Any]:
    trace = read_trace(trace_path)
    corpus = load_corpus(load_lock(settings.corpus_lock), settings.corpus_dir)
    if corpus.sha256 != trace.header.corpus_sha256:
        raise ValueError("trace was generated from a different corpus; regenerate the trace")
    needs_sqs = any(isinstance(r, IndexingRequest) for r in trace.requests)
    sqs = aws.client("sqs", settings) if needs_sqs else None
    limits = httpx.Limits(max_connections=None, max_keepalive_connections=None)
    timeout = httpx.Timeout(settings.inference_timeout_s, connect=5.0)
    async with httpx.AsyncClient(
        base_url=settings.gateway_url, limits=limits, timeout=timeout
    ) as http:
        gw_metrics = f"{settings.gateway_url}/metrics/"
        before = (
            (await _scrape(http, settings.inference_metrics_url), await _scrape(http, gw_metrics))
            if do_reconcile
            else (None, None)
        )
        replayer = Replayer(settings, corpus, http, sqs)
        records = await replayer.run(trace)
        after = (
            (await _scrape(http, settings.inference_metrics_url), await _scrape(http, gw_metrics))
            if do_reconcile
            else (None, None)
        )

    check = selfcheck.check(
        [r.intended_send_s for r in records],
        [r.actual_send_s for r in records],
        replayer.cpu_samples,
    )
    streamed = [r for r in records if r.workload != "indexing" and r.status == "ok"]
    recon = (
        reconcile.reconcile(
            [r.ttft_s for r in streamed if r.ttft_s is not None],
            len(streamed),
            before[0],
            after[0],
            before[1],
            after[1],
        )
        if do_reconcile
        else None
    )
    run_id = f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{trace.header.trace_id}"
    raw_path = out_dir / "raw" / f"{run_id}.jsonl"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text("".join(json.dumps(asdict(r)) + "\n" for r in records))
    summary = summarize(run_id, settings, trace, trace_path, records, check, recon)
    (out_dir / f"{run_id}.summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, default=Path("results"))
    parser.add_argument("--no-reconcile", action="store_true")
    args = parser.parse_args(argv)
    started = time.monotonic()
    summary = asyncio.run(
        run_trace(args.trace, args.out_dir, get_settings(), not args.no_reconcile)
    )
    verdict = "VALID" if summary["valid"] else "INVALID"
    print(f"{verdict} run {summary['run_id']} in {time.monotonic() - started:.1f}s")
    for reason in summary["self_check"]["reasons"]:
        print(f"  self-check: {reason}")
    recon = summary["reconciliation"]
    if recon:
        print(f"  reconciliation: {recon['status']}")
        for line in recon["problems"] + recon["notes"]:
            print(f"    {line}")


if __name__ == "__main__":
    main()
