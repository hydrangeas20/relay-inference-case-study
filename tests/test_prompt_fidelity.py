import dataclasses
from pathlib import Path

import httpx
import numpy as np
import pytest

from relay import prompts
from relay.config import Settings
from relay.corpus.store import Corpus, CorpusFile
from relay.gateway.app import PROMPT_CHARS_HEADER, create_app
from relay.traces.schema import CompletionRequest
from relay.traffic.check import ks_critical, ks_statistic, prompt_size_report
from relay.traffic.generate import MIN_PREFIX_CHARS, TraceSpec, generate_traffic
from relay.traffic.model import load_model
from tests.fakes import FakeConfig, create_fake_inference

ROOT = Path(__file__).resolve().parents[1]
MODEL = load_model(ROOT / "traffic" / "relay.toml")


@pytest.fixture
def sized_corpus() -> Corpus:
    """Files long enough for any Azure-derived target (max ~27K characters)."""
    files = []
    for repo in ("alpha", "beta"):
        for i in range(6):
            n = 400 + 150 * i
            text = "".join(f"def {repo}_{i}_{k}(x):\n    return x * {k} + 1\n\n" for k in range(n))
            files.append(CorpusFile(repo=repo, language="python", path=f"src/m{i}.py", text=text))
    return Corpus(files, sha256="1" * 64)


async def _built(corpus: Corpus, comps: list[CompletionRequest]) -> dict[str, int]:
    settings = Settings(_env_file=None, inference_base_url="http://inference/v1")  # type: ignore[call-arg]
    app = create_app(
        settings,
        transport=httpx.ASGITransport(app=create_fake_inference(FakeConfig(chunks=1, ttft_s=0))),
    )
    out = {}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://gw") as c:
        for r in comps:
            resp = await c.post("/v1/complete", json=prompts.completion_payload(r, corpus))
            assert resp.status_code == 200
            out[r.req_id] = int(resp.headers[PROMPT_CHARS_HEADER])
    return out


async def test_gateway_builds_exactly_the_expected_size(sized_corpus: Corpus) -> None:
    spec = TraceSpec(kind="window", peak_rps=20, seed=7, start_utc_s=15 * 3600, duration_s=60)
    _, reqs = generate_traffic(MODEL, sized_corpus, spec)
    comps = [r for r in reqs if isinstance(r, CompletionRequest)]
    built = await _built(sized_corpus, comps)
    assert all(built[r.req_id] == r.expected_prompt_chars for r in comps)
    for r in comps:
        target = round(r.target_prompt_tokens * MODEL.chars_per_token)
        if r.below_template_minimum:
            assert built[r.req_id] > target
        else:
            assert built[r.req_id] == target  # representable targets are built exactly


async def test_below_minimum_targets_are_kept_and_flagged(sized_corpus: Corpus) -> None:
    tiny = dataclasses.replace(MODEL, completion_sizes=np.array([[5, 3]]))
    spec = TraceSpec(kind="window", peak_rps=20, seed=1, start_utc_s=15 * 3600, duration_s=30)
    _, reqs = generate_traffic(tiny, sized_corpus, spec)
    comps = [r for r in reqs if isinstance(r, CompletionRequest)]
    assert comps and all(r.below_template_minimum and r.target_prompt_tokens == 5 for r in comps)
    assert all(r.prefix_chars == MIN_PREFIX_CHARS and not r.context_files for r in comps)
    built = await _built(sized_corpus, comps)
    report = prompt_size_report(comps, built, MODEL.chars_per_token)
    assert report.below_minimum_fraction == 1.0 and report.expected_mismatch == 0
    assert min(report.below_minimum_inflation) > 1


def test_context_files_are_full_length(sized_corpus: Corpus) -> None:
    spec = TraceSpec(kind="window", peak_rps=20, seed=3, start_utc_s=15 * 3600, duration_s=120)
    _, reqs = generate_traffic(MODEL, sized_corpus, spec)
    for r in reqs:
        if isinstance(r, CompletionRequest):
            for c in r.context_files:
                assert len(sized_corpus.get(c.repo, c.path).text) >= prompts.CONTEXT_FILE_CHARS


def test_ks_helpers() -> None:
    a = np.arange(1000.0)
    assert ks_statistic(a, a) == 0.0
    assert ks_statistic(a, a + 1000) == 1.0
    assert ks_critical(100, 100) == pytest.approx(1.358 * np.sqrt(0.02))
