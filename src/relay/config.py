"""Runtime configuration, read from environment variables (see .env.example)."""

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

ResultSource = Literal["gpu", "sim", "projection", "floci"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Inference: the only switch between the real GPU and the simulator.
    inference_base_url: str = "http://localhost:8000/v1"
    inference_metrics_url: str = "http://localhost:8000/metrics"
    inference_backend: ResultSource = "sim"
    completion_model: str = "relay/code-7b"
    embedding_model: str = "relay/embed-small"
    inference_timeout_s: float = 60.0

    # Gateway (Relay's API).
    gateway_url: str = "http://localhost:8080"
    gateway_port: int = 8080

    # Customer AWS: Floci locally, real AWS if this is unset.
    aws_endpoint_url: str | None = "http://localhost:4566"
    aws_region: str = "us-east-1"
    indexing_queue_name: str = "relay-indexing"
    results_table_name: str = "relay-index-results"

    # Indexing worker.
    worker_max_in_flight: int = 8
    worker_metrics_port: int = 9101
    worker_poll_wait_s: int = 5
    worker_visibility_timeout_s: int = 60

    # Code corpus used to build prompts.
    corpus_manifest: Path = Path("corpus/repos.toml")
    corpus_lock: Path = Path("corpus/corpus.lock.json")
    corpus_dir: Path = Path("data/corpus")


def get_settings() -> Settings:
    return Settings()
