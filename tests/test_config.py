import pytest

from relay.config import Settings


def test_defaults_point_at_local_stack() -> None:
    settings = Settings(_env_file=None)
    assert settings.inference_base_url == "http://localhost:8000/v1"
    assert settings.inference_backend == "sim"
    assert settings.aws_endpoint_url == "http://localhost:4566"


def test_env_switches_to_real_gpu(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INFERENCE_BASE_URL", "http://gpu-host:8000/v1")
    monkeypatch.setenv("INFERENCE_BACKEND", "gpu")
    settings = Settings(_env_file=None)
    assert settings.inference_base_url == "http://gpu-host:8000/v1"
    assert settings.inference_backend == "gpu"


def test_rejects_unknown_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INFERENCE_BACKEND", "vibes")
    with pytest.raises(ValueError):
        Settings(_env_file=None)


def test_send_lag_limit_is_unset_unless_an_experiment_sets_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert Settings(_env_file=None).loadgen_send_lag_p99_limit_ms is None
    monkeypatch.setenv("LOADGEN_SEND_LAG_P99_LIMIT_MS", "10")
    assert Settings(_env_file=None).loadgen_send_lag_p99_limit_ms == 10.0
