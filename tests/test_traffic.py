from pathlib import Path

import numpy as np
import pytest

from relay.corpus.store import Corpus
from relay.traces.io import dumps, read_trace, write_trace
from relay.traces.schema import CompletionRequest, IndexingRequest
from relay.traffic.burstiness import OutOfRangeError
from relay.traffic.check import check_envelope
from relay.traffic.generate import TraceSpec, generate_traffic
from relay.traffic.model import SECONDS_PER_DAY, load_model

ROOT = Path(__file__).resolve().parents[1]
MODEL = load_model(ROOT / "traffic" / "relay.toml")
REFERENCE = ROOT / "traffic" / "reference"


def test_envelope_peak_to_trough_within_azure_training_weekdays() -> None:
    result = check_envelope(MODEL, REFERENCE / "azure_code_hourly.csv")
    assert result.passed, result
    assert (result.azure_weekday_min, result.azure_weekday_max) == (8.61, 11.29)


def test_reference_hourly_file_holds_training_days_only() -> None:
    days = {
        line.split(",")[1]
        for line in (REFERENCE / "azure_code_hourly.csv").read_text().splitlines()[1:]
    }
    assert days == {"Fri", "Sat", "Sun", "Mon", "Tue"}


def test_envelope_integrates_to_daily_volume() -> None:
    t = np.arange(0, SECONDS_PER_DAY, 1.0)
    rates = MODEL.interactive_rate_rps(t)
    for workload, daily in MODEL.daily_requests().items():
        assert rates[workload].sum() == pytest.approx(daily, rel=1e-3)


def test_window_count_matches_scaled_envelope(small_corpus: Corpus) -> None:
    spec = TraceSpec(kind="window", peak_rps=10, seed=2, start_utc_s=15 * 3600, duration_s=1200)
    header, reqs = generate_traffic(MODEL, small_corpus, spec)
    t = spec.start_utc_s + np.arange(0, spec.duration_s, 1.0)
    expected = sum(MODEL.interactive_rate_rps(t).values()).sum() * header.scale
    interactive = [r for r in reqs if not isinstance(r, IndexingRequest)]
    assert len(interactive) == pytest.approx(expected, rel=0.08)
    assert header.params["users_represented"] == pytest.approx(
        MODEL.daily_active_users * header.scale, rel=1e-3
    )


def test_header_records_burstiness_provenance(small_corpus: Corpus) -> None:
    spec = TraceSpec(kind="window", peak_rps=10, seed=2, start_utc_s=15 * 3600, duration_s=300)
    header, _ = generate_traffic(MODEL, small_corpus, spec)
    p = header.params
    assert p["burstiness_candidate"] == MODEL.burstiness.name
    assert p["observed_range_rps"] == [MODEL.burstiness.rate_min, MODEL.burstiness.rate_max]
    assert p["out_of_range_fraction"] == 0.0
    assert p["scenario"] is None and p["clustered"] is False


def test_out_of_range_trace_requires_a_scenario(small_corpus: Corpus) -> None:
    # A peak of 1 rps is below Azure's observed range (3.2 rps) all day.
    spec = TraceSpec(kind="window", peak_rps=1, seed=1, start_utc_s=15 * 3600, duration_s=60)
    with pytest.raises(OutOfRangeError):
        generate_traffic(MODEL, small_corpus, spec)
    header, _ = generate_traffic(
        MODEL, small_corpus, TraceSpec(**{**spec.__dict__, "scenario": "edge"})
    )
    assert header.params["out_of_range_fraction"] == 1.0


def test_same_spec_gives_identical_trace(small_corpus: Corpus) -> None:
    spec = TraceSpec(kind="window", peak_rps=5, seed=9, start_utc_s=15 * 3600, duration_s=300)
    a, b = generate_traffic(MODEL, small_corpus, spec), generate_traffic(MODEL, small_corpus, spec)
    assert dumps(*a) == dumps(*b)


def test_indexing_only_in_nightly_window(small_corpus: Corpus) -> None:
    start = MODEL.indexing_window_start_utc_h * 3600
    inside = TraceSpec(
        kind="window", peak_rps=50, seed=1, start_utc_s=start, duration_s=600, scenario="edge"
    )
    outside = TraceSpec(kind="window", peak_rps=50, seed=1, start_utc_s=15 * 3600, duration_s=600)
    _, reqs_in = generate_traffic(MODEL, small_corpus, inside)
    _, reqs_out = generate_traffic(MODEL, small_corpus, outside)
    assert any(isinstance(r, IndexingRequest) for r in reqs_in)
    assert not any(isinstance(r, IndexingRequest) for r in reqs_out)


def test_completions_carry_azure_sized_targets(small_corpus: Corpus) -> None:
    spec = TraceSpec(kind="window", peak_rps=20, seed=4, start_utc_s=15 * 3600, duration_s=300)
    _, reqs = generate_traffic(MODEL, small_corpus, spec)
    comps = [r for r in reqs if isinstance(r, CompletionRequest)]
    assert comps
    allowed_ctx = set(MODEL.completion_sizes[:, 0].tolist())
    for r in comps:
        assert r.target_prompt_tokens in allowed_ctx or r.target_prompt_tokens == 1
        assert r.max_tokens == r.target_output_tokens
        assert r.expected_prompt_chars is not None


def test_trace_roundtrip_v3(small_corpus: Corpus, tmp_path: Path) -> None:
    spec = TraceSpec(kind="window", peak_rps=5, seed=1, start_utc_s=15 * 3600, duration_s=120)
    header, reqs = generate_traffic(MODEL, small_corpus, spec)
    write_trace(tmp_path / "t.jsonl", header, reqs)
    trace = read_trace(tmp_path / "t.jsonl")
    assert trace.header.format_version == 3
    assert trace.header.traffic_model_sha256 == MODEL.sha256
    assert trace.requests == reqs


def test_reads_v1_traces() -> None:
    trace = read_trace(ROOT / "tests" / "data" / "trace_v1.jsonl")
    assert trace.header.format_version == 1
    assert trace.header.kind == "constant"


@pytest.mark.parametrize(
    "spec",
    [
        TraceSpec(kind="day", peak_rps=5, seed=1, start_utc_s=3600),
        TraceSpec(kind="window", peak_rps=0, seed=1, duration_s=60),
        TraceSpec(kind="weekly", peak_rps=5, seed=1),
        TraceSpec(kind="window", peak_rps=5, seed=1, start_utc_s=SECONDS_PER_DAY, duration_s=60),
        TraceSpec(kind="window", peak_rps=5, seed=1, duration_s=60, scenario="guess"),  # type: ignore[arg-type]
    ],
)
def test_invalid_specs_rejected(spec: TraceSpec) -> None:
    with pytest.raises(ValueError):
        spec.validate()
