import asyncio
import json
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from moto import mock_aws

from relay import aws
from relay.config import Settings
from relay.worker import IndexWorker
from tests.fakes import FakeConfig, create_fake_inference


@pytest.fixture
def aws_env() -> Iterator[tuple[Settings, Any, Any]]:
    with mock_aws():
        settings = Settings(  # type: ignore[call-arg]
            _env_file=None,
            aws_endpoint_url=None,
            worker_max_in_flight=3,
            worker_poll_wait_s=0,
        )
        sqs, ddb = aws.client("sqs", settings), aws.client("dynamodb", settings)
        aws.bootstrap(settings, sqs, ddb)
        yield settings, sqs, ddb


def _enqueue(sqs: Any, settings: Settings, n: int) -> None:
    url = aws.queue_url(sqs, settings)
    for i in range(n):
        body = {"job_id": f"job{i}", "repo": "demo", "paths": ["a.py"], "chunks": ["x", "y"]}
        sqs.send_message(QueueUrl=url, MessageBody=json.dumps(body))


async def _run_until_idle(worker: IndexWorker, sqs: Any, settings: Settings) -> None:
    stop = asyncio.Event()
    task = asyncio.create_task(worker.run(stop))
    url = aws.queue_url(sqs, settings)
    for _ in range(200):
        await asyncio.sleep(0.05)
        attrs = sqs.get_queue_attributes(QueueUrl=url, AttributeNames=["All"])["Attributes"]
        if attrs["ApproximateNumberOfMessages"] == "0" and not worker._in_flight:
            break
    stop.set()
    await asyncio.wait_for(task, timeout=5)


def test_bootstrap_is_idempotent(aws_env: tuple[Settings, Any, Any]) -> None:
    settings, sqs, ddb = aws_env
    aws.bootstrap(settings, sqs, ddb)


async def test_jobs_are_embedded_recorded_and_deleted(aws_env: tuple[Settings, Any, Any]) -> None:
    settings, sqs, ddb = aws_env
    _enqueue(sqs, settings, 9)
    fake = create_fake_inference(FakeConfig(embed_delay_s=0.05, embed_dims=8))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=fake), base_url="http://inference/v1"
    ) as http:
        worker = IndexWorker(settings, sqs, ddb, http)
        await _run_until_idle(worker, sqs, settings)

    items = ddb.scan(TableName=settings.results_table_name)["Items"]
    assert len(items) == 9
    assert {i["status"]["S"] for i in items} == {"ok"}
    assert {i["embedding_dims"]["N"] for i in items} == {"8"}
    assert 1 < worker.max_observed_in_flight <= settings.worker_max_in_flight


async def test_failed_job_is_left_on_queue_for_retry(aws_env: tuple[Settings, Any, Any]) -> None:
    settings, sqs, ddb = aws_env
    _enqueue(sqs, settings, 1)
    fake = create_fake_inference(FakeConfig(fail_status=500))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=fake), base_url="http://inference/v1"
    ) as http:
        worker = IndexWorker(settings, sqs, ddb, http)
        stop = asyncio.Event()
        task = asyncio.create_task(worker.run(stop))
        await asyncio.sleep(0.5)
        stop.set()
        await asyncio.wait_for(task, timeout=5)

    assert ddb.scan(TableName=settings.results_table_name)["Items"] == []
    url = aws.queue_url(sqs, settings)
    attrs = sqs.get_queue_attributes(QueueUrl=url, AttributeNames=["All"])["Attributes"]
    assert int(attrs["ApproximateNumberOfMessagesNotVisible"]) == 1


def test_rejects_zero_concurrency(aws_env: tuple[Settings, Any, Any]) -> None:
    settings, sqs, ddb = aws_env
    bad = settings.model_copy(update={"worker_max_in_flight": 0})
    with pytest.raises(ValueError):
        IndexWorker(bad, sqs, ddb, httpx.AsyncClient())
