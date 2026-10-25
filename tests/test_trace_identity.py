import subprocess
import sys
from pathlib import Path

import pytest

from relay.corpus.store import Corpus
from relay.traces import identity
from relay.traces.io import TraceFormatError, read_trace, request_lines, write_trace
from relay.traffic.generate import TraceSpec, generate_traffic
from relay.traffic.model import load_model

ROOT = Path(__file__).resolve().parents[1]
MODEL = load_model(ROOT / "traffic" / "relay.toml")
SPEC = TraceSpec(kind="window", peak_rps=10, seed=3, start_utc_s=15 * 3600, duration_s=120)


def test_trace_id_is_the_hash_of_the_request_lines(small_corpus: Corpus, tmp_path: Path) -> None:
    header, reqs = generate_traffic(MODEL, small_corpus, SPEC)
    write_trace(tmp_path / "t.jsonl", header, reqs)
    trace = read_trace(tmp_path / "t.jsonl")
    assert trace.header.trace_id == identity.content_trace_id(request_lines(reqs))
    assert len(trace.header.trace_id) == 64


def test_edited_trace_is_rejected(small_corpus: Corpus, tmp_path: Path) -> None:
    header, reqs = generate_traffic(MODEL, small_corpus, SPEC)
    path = tmp_path / "t.jsonl"
    write_trace(path, header, reqs)
    lines = path.read_text().splitlines()
    lines[1] = (
        lines[1].replace('"max_tokens":', '"max_tokens":1', 1)
        if '"max_tokens":' in lines[1]
        else lines[1]
    )
    lines[-1] = lines[-1].replace("r0000", "r9999", 1)
    path.write_text("\n".join(lines) + "\n")
    with pytest.raises(TraceFormatError):
        read_trace(path)


def test_same_spec_same_ids_different_spec_different_ids(small_corpus: Corpus) -> None:
    h1, r1 = generate_traffic(MODEL, small_corpus, SPEC)
    h2, r2 = generate_traffic(MODEL, small_corpus, SPEC)
    h3, r3 = generate_traffic(MODEL, small_corpus, TraceSpec(**{**SPEC.__dict__, "seed": 4}))
    ids = [identity.content_trace_id(request_lines(r)) for r in (r1, r2, r3)]
    assert h1.spec_id == h2.spec_id != h3.spec_id
    assert ids[0] == ids[1] != ids[2]
    assert h1.generator_sha256 == h2.generator_sha256 == h3.generator_sha256


def test_code_change_changes_generator_hash_not_spec_id(
    small_corpus: Corpus, monkeypatch: pytest.MonkeyPatch
) -> None:
    h1, _ = generate_traffic(MODEL, small_corpus, SPEC)
    real = identity.generator_sha256
    monkeypatch.setattr(identity, "generator_sha256", lambda: "0" * 64 if real() else "")
    h2, _ = generate_traffic(MODEL, small_corpus, SPEC)
    assert h1.spec_id == h2.spec_id
    assert h1.generator_sha256 != h2.generator_sha256


def test_generator_hash_covers_every_relay_module_the_generator_imports() -> None:
    code = (
        "import sys, relay.traces.generate, relay.traffic.generate;"
        "print('\\n'.join(sorted(m for m in sys.modules if m.startswith('relay.'))))"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    imported = {m for m in out.stdout.split() if m}
    packages = {"relay.corpus", "relay.gateway", "relay.traces", "relay.traffic"}
    missing = imported - set(identity.GENERATOR_MODULES) - packages
    assert not missing, f"add to identity.GENERATOR_MODULES: {sorted(missing)}"


def test_spec_id_is_canonical() -> None:
    assert identity.spec_id({"a": 1, "b": 2}) == identity.spec_id({"b": 2, "a": 1})
