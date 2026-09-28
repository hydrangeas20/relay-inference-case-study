"""AWS clients and resource bootstrap. Works against Floci locally and real AWS unchanged."""

from __future__ import annotations

import time
from typing import Any

import boto3
from botocore.exceptions import ClientError

from relay.config import Settings, get_settings


def client(service: str, settings: Settings) -> Any:
    return boto3.client(
        service,
        endpoint_url=settings.aws_endpoint_url,
        region_name=settings.aws_region,
    )


def queue_url(sqs: Any, settings: Settings) -> str:
    return str(sqs.get_queue_url(QueueName=settings.indexing_queue_name)["QueueUrl"])


def bootstrap(settings: Settings, sqs: Any, dynamodb: Any, timeout_s: float = 30.0) -> None:
    """Create the indexing queue and results table. Safe to run repeatedly."""
    sqs.create_queue(
        QueueName=settings.indexing_queue_name,
        Attributes={"VisibilityTimeout": str(settings.worker_visibility_timeout_s)},
    )
    try:
        dynamodb.create_table(
            TableName=settings.results_table_name,
            AttributeDefinitions=[{"AttributeName": "job_id", "AttributeType": "S"}],
            KeySchema=[{"AttributeName": "job_id", "KeyType": "HASH"}],
            BillingMode="PAY_PER_REQUEST",
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "ResourceInUseException":
            raise
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        status = dynamodb.describe_table(TableName=settings.results_table_name)["Table"][
            "TableStatus"
        ]
        if status == "ACTIVE":
            return
        time.sleep(0.5)
    raise TimeoutError(f"table {settings.results_table_name} did not become ACTIVE")


def main() -> None:
    settings = get_settings()
    bootstrap(settings, client("sqs", settings), client("dynamodb", settings))
    print(f"ready: queue {settings.indexing_queue_name}, table {settings.results_table_name}")


if __name__ == "__main__":
    main()
