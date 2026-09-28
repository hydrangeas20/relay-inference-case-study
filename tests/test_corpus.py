import hashlib
from pathlib import Path

import pytest

from relay.corpus.fetch import LicenseMismatchError, check_license, select_files
from relay.corpus.manifest import CorpusLock, LockedFile, RepoSpec, load_manifest
from relay.corpus.store import CorpusIntegrityError, load_corpus

REPO_ROOT = Path(__file__).resolve().parents[1]


def _spec(**overrides: object) -> RepoSpec:
    base: dict[str, object] = {
        "name": "demo",
        "url": "https://example.invalid/demo",
        "commit": "a" * 40,
        "language": "python",
        "extensions": [".py"],
        "include_dirs": ["src"],
        "license": "MIT",
        "license_file": "LICENSE",
        "license_sha256": hashlib.sha256(b"MIT License\n").hexdigest(),
        "max_files": 3,
        "min_bytes": 10,
        "max_bytes": 1000,
    }
    return RepoSpec(**{**base, **overrides})  # type: ignore[arg-type]


def test_committed_manifest_is_valid() -> None:
    manifest = load_manifest(REPO_ROOT / "corpus" / "repos.toml")
    assert len(manifest.repos) >= 5
    assert len({r.language for r in manifest.repos}) == len(manifest.repos)


def test_manifest_rejects_disallowed_license() -> None:
    with pytest.raises(ValueError):
        _spec(license="GPL-3.0")


def test_select_files_filters_and_is_deterministic(tmp_path: Path) -> None:
    (tmp_path / "src" / "pkg").mkdir(parents=True)
    for i in range(6):
        (tmp_path / "src" / "pkg" / f"m{i}.py").write_text("x = 1\n" * 10)
    (tmp_path / "src" / "tiny.py").write_text("x")  # below min_bytes
    (tmp_path / "src" / "notes.md").write_text("# not code\n" * 10)
    (tmp_path / "other.py").write_text("x = 1\n" * 10)  # outside include_dirs
    spec = _spec()
    first, second = select_files(spec, tmp_path), select_files(spec, tmp_path)
    assert first == second
    assert len(first) == 3
    assert all(p.suffix == ".py" and p.parts[0] == "src" for p in first)


def test_license_hash_mismatch_is_refused(tmp_path: Path) -> None:
    (tmp_path / "LICENSE").write_text("Some other license\n")
    with pytest.raises(LicenseMismatchError):
        check_license(_spec(), tmp_path)


def test_license_hash_match_passes(tmp_path: Path) -> None:
    (tmp_path / "LICENSE").write_text("MIT License\n")
    check_license(_spec(), tmp_path)


def test_corpus_detects_tampered_file(tmp_path: Path) -> None:
    (tmp_path / "demo" / "src").mkdir(parents=True)
    path = tmp_path / "demo" / "src" / "a.py"
    path.write_text("print('hi')\n")
    lock = CorpusLock(
        manifest_sha256="0" * 64,
        files=[
            LockedFile(
                repo="demo",
                language="python",
                path="src/a.py",
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                bytes=12,
            )
        ],
    )
    assert load_corpus(lock, tmp_path).get("demo", "src/a.py").text == "print('hi')\n"
    path.write_text("print('changed')\n")
    with pytest.raises(CorpusIntegrityError):
        load_corpus(lock, tmp_path)
