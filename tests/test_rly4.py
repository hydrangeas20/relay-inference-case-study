"""RLY-4 regression tests: the template fix, the session traces and the evidence plumbing.

None of these need a model. They pin the properties the experiment relies on: with the
original template no two prompts share more than a few characters, with the fix each
request in a session extends the previous prompt exactly, and the shared and
independent traces differ only in which file each request uses.
"""

from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from relay import manifest
from relay.config import Settings
from relay.corpus.store import Corpus, CorpusFile
from relay.gateway import templates
from relay.gateway.app import REQUEST_ID_HEADER, create_app
from relay.loadgen.runner import RequestRecord, server_timing_summary
from relay.sse import chunk_timings
from relay.traces.schema import CompletionRequest
from relay.traces.sessions import SessionParams, generate_sessions
from tests.fakes import create_fake_inference

T0 = datetime(2026, 10, 25, 12, 0, 0, tzinfo=UTC)
T1 = datetime(2026, 10, 25, 12, 0, 1, tzinfo=UTC)
FILE = "".join(f"def fn_{i}(x):\n    return x + {i}\n\n" for i in range(200))


def _prompt(request_id: str, cursor: int, now: datetime, variant: Any) -> str:
    return templates.completion_prompt(
        request_id=request_id,
        repo="demo",
        file_path="src/app.py",
        language="python",
        prefix=FILE[:cursor],
        context_files=[],
        now=now,
        variant=variant,
    )


def _common_prefix(a: str, b: str) -> int:
    return len(os.path.commonprefix([a, b]))


# --- the template (the mechanism RLY-4 is about) -------------------------------------


def test_original_template_prompts_diverge_within_the_header() -> None:
    """The bug: two requests with identical code share only the header's opening text."""
    a = _prompt("s000-00", 2000, T0, "original")
    b = _prompt("s000-01", 2000, T1, "original")
    assert a != b
    assert _common_prefix(a, b) < len("[relay request_id=s000-0") + 1


def test_original_template_is_unchanged() -> None:
    """The baseline must stay byte-for-byte Relay's, or the before/after loses meaning."""
    p = _prompt("r1", 10, T0, "original")
    assert p.startswith("[relay request_id=r1 ts=2026-10-25T12:00:00.000+00:00]\n")
    assert p.endswith(f"--- src/app.py (python) ---\n{FILE[:10]}")


def test_metadata_template_has_no_per_request_content() -> None:
    a = _prompt("s000-00", 2000, T0, "metadata")
    b = _prompt("other-id", 2000, T1, "metadata")
    assert a == b
    assert "request_id" not in a and "ts=" not in a


def test_metadata_template_session_prompts_extend_each_other() -> None:
    """The fix: each later request in a session starts with the whole earlier prompt,
    so a prefix cache can reuse all of it."""
    cursors = [2000, 2100, 2340, 2500]
    prompts = [_prompt(f"s000-{k:02d}", c, T0, "metadata") for k, c in enumerate(cursors)]
    for earlier, later in zip(prompts, prompts[1:], strict=False):
        assert later.startswith(earlier)


def test_agent_messages_follow_the_variant() -> None:
    kw: dict[str, Any] = {
        "request_id": "a1",
        "repo": "demo",
        "file_path": "f.py",
        "language": "python",
        "file_content": "x = 1",
        "question": "q?",
        "now": T0,
    }
    orig = templates.agent_messages(**kw, variant="original")
    fixed = templates.agent_messages(**kw, variant="metadata")
    assert orig[0]["content"].startswith("[relay request_id=a1")
    assert fixed[0]["content"] == templates.SYSTEM_PROMPT


# --- the gateway carries the request ID outside the prompt ----------------------------


@pytest.mark.parametrize("variant", ["original", "metadata"])
async def test_gateway_info_and_request_id_header(variant: str) -> None:
    fake = create_fake_inference()
    seen: list[httpx.Request] = []
    inner = httpx.ASGITransport(app=fake)

    class Spy(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return await inner.handle_async_request(request)

    settings = Settings(  # type: ignore[call-arg]
        _env_file=None, inference_base_url="http://inference/v1", prompt_template=variant
    )
    app = create_app(settings, transport=Spy())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://gw"
    ) as gw:
        info = (await gw.get("/info")).json()
        assert info["prompt_template"] == variant
        body = {
            "request_id": "req-42",
            "repo": "demo",
            "file_path": "a.py",
            "language": "python",
            "prefix": "def f():\n    ",
            "context_files": [],
            "max_tokens": 4,
        }
        resp = await gw.post("/v1/complete", json=body)
        assert resp.status_code == 200
    upstream = seen[-1]
    assert upstream.headers[REQUEST_ID_HEADER] == "req-42"
    prompt = httpx.Response(200, content=upstream.content).json()["prompt"]
    assert ("req-42" in prompt) is (variant == "original")


# --- session traces --------------------------------------------------------------------


@pytest.fixture
def long_corpus() -> Corpus:
    files = [
        CorpusFile(repo=r, language="python", path=f"m{i}.py", text=FILE)
        for r in ("alpha", "beta")
        for i in range(10)
    ]
    return Corpus(files, sha256="0" * 64)


def _params(**kw: Any) -> SessionParams:
    base: dict[str, Any] = {"n_sessions": 3, "per_session": 4, "rate_rps": 1.0, "seed": 7}
    return SessionParams(**{**base, **kw})


def test_shared_and_independent_share_one_schedule(long_corpus: Corpus) -> None:
    shared = generate_sessions(long_corpus, _params())
    indep = generate_sessions(long_corpus, _params(shared=False))
    assert [r.send_at_s for r in shared] == [r.send_at_s for r in indep]
    assert [r.cursor for r in shared] == [r.cursor for r in indep]  # type: ignore[union-attr]
    assert len({r.file.path + r.file.repo for r in indep}) == len(indep)  # type: ignore[union-attr]


def test_shared_sessions_stay_in_one_file_and_move_forward(long_corpus: Corpus) -> None:
    reqs = [
        r for r in generate_sessions(long_corpus, _params()) if isinstance(r, CompletionRequest)
    ]
    for s in range(3):
        session = reqs[s * 4 : (s + 1) * 4]
        assert len({(r.file.repo, r.file.path) for r in session}) == 1
        cursors = [r.cursor for r in session]
        assert cursors == sorted(cursors) and len(set(cursors)) == 4
        assert all(r.prefix_chars == r.cursor and r.suffix_chars == 0 for r in session)


def test_session_trace_is_deterministic(long_corpus: Corpus) -> None:
    a = generate_sessions(long_corpus, _params())
    b = generate_sessions(long_corpus, _params())
    assert [r.model_dump() for r in a] == [r.model_dump() for r in b]


def test_independent_needs_enough_distinct_files(long_corpus: Corpus) -> None:
    with pytest.raises(ValueError, match="distinct files"):
        generate_sessions(long_corpus, _params(n_sessions=6, per_session=4, shared=False))


# --- backend timings and the summary --------------------------------------------------

LLAMA_FINAL = (
    'data: {"choices":[{"text":"","finish_reason":"length"}],'
    '"timings":{"cache_n":533,"prompt_n":41,"prompt_ms":192.3,"predicted_n":8,"flag":true}}'
)


def test_chunk_timings_reads_llama_cpp_final_chunk() -> None:
    assert chunk_timings(LLAMA_FINAL) == {
        "cache_n": 533.0,
        "prompt_n": 41.0,
        "prompt_ms": 192.3,
        "predicted_n": 8.0,
    }


@pytest.mark.parametrize(
    "line",
    ['data: {"choices":[{"text":"abc"}]}', "data: [DONE]", "", 'data: {"timings": 3}'],
)
def test_chunk_timings_absent(line: str) -> None:
    assert chunk_timings(line) is None


def _rec(timings: dict[str, float] | None) -> RequestRecord:
    return RequestRecord("r", "completion", 0.0, 0.0, "ok", server_timings=timings)


def test_server_timing_summary() -> None:
    s = server_timing_summary(
        [
            _rec({"cache_n": 0, "prompt_n": 1000, "prompt_ms": 900.0}),
            _rec({"cache_n": 900, "prompt_n": 100, "prompt_ms": 120.0}),
            _rec(None),
        ]
    )
    assert s is not None
    assert s["requests_with_timings"] == 2
    assert s["prompt_tokens_cached"] == 900 and s["prompt_tokens_evaluated"] == 1100
    assert s["cached_fraction"] == pytest.approx(0.45)
    assert server_timing_summary([_rec(None)]) is None


# --- manifest ----------------------------------------------------------------------------


async def test_manifest_records_llama_cpp_identity(tmp_path: Any) -> None:
    model = tmp_path / "m.gguf"
    model.write_bytes(b"weights")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "m"}]})
        if request.url.path == "/props":
            return httpx.Response(
                200,
                json={
                    "build_info": "b1-abc",
                    "model_path": str(model),
                    "total_slots": 1,
                    "default_generation_settings": {"n_ctx": 4096},
                },
            )
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        info = await manifest.inference_server(http, "http://srv/v1")
    assert info["engine"] == "llama.cpp"
    lc = info["llama_cpp"]
    assert lc["build_info"] == "b1-abc" and lc["n_ctx"] == 4096
    assert lc["model_sha256"] == hashlib.sha256(b"weights").hexdigest()


async def test_manifest_without_props_is_not_llama_cpp() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": []})
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        info = await manifest.inference_server(http, "http://srv/v1")
    assert "engine" not in info and info["models"] == {"data": []}


def test_git_info_reports_commit() -> None:
    g = manifest.git_info()
    assert g["commit"] is None or len(g["commit"]) == 40
