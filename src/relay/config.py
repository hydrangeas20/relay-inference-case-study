"""Runtime configuration, read from environment variables (see .env.example)."""

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

ResultSource = Literal["gpu", "sim", "projection", "floci"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Inference: the only switch between the real GPU and the simulator.
    inference_base_url: str = "http://localhost:8000/v1"
    inference_backend: ResultSource = "sim"
    completion_model: str = "relay/code-7b"
    embedding_model: str = "relay/embed-small"

    # Customer AWS: Floci locally, real AWS if this is unset.
    aws_endpoint_url: str | None = "http://localhost:4566"
    aws_region: str = "us-east-1"
    indexing_queue_name: str = "relay-indexing"
    results_table_name: str = "relay-index-results"


def get_settings() -> Settings:
    return Settings()
