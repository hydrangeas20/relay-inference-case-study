"""Build the local code corpus from the pinned repos.

Usage: relay-corpus [--verify-only]

For each repo in corpus/repos.toml: shallow-fetch the pinned commit with git,
check the license file's SHA-256 against the reviewed value, select source files
deterministically, copy them into data/corpus/<repo>/, and record every file's
SHA-256 in corpus/corpus.lock.json.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from relay.config import get_settings
from relay.corpus.manifest import (
    CorpusLock,
    LockedFile,
    Manifest,
    RepoSpec,
    load_manifest,
    write_lock,
)


class LicenseMismatchError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checkout(spec: RepoSpec, dest: Path) -> None:
    """Shallow-fetch exactly the pinned commit into dest."""
    dest.mkdir(parents=True, exist_ok=True)
    for cmd in (
        ["git", "init", "-q"],
        ["git", "fetch", "-q", "--depth", "1", spec.url, spec.commit],
        ["git", "checkout", "-q", "FETCH_HEAD"],
    ):
        subprocess.run(cmd, cwd=dest, check=True)


def check_license(spec: RepoSpec, checkout_dir: Path) -> None:
    license_path = checkout_dir / spec.license_file
    if not license_path.is_file():
        raise LicenseMismatchError(f"{spec.name}: {spec.license_file} not found at {spec.commit}")
    actual = sha256_file(license_path)
    if actual != spec.license_sha256:
        raise LicenseMismatchError(
            f"{spec.name}: license file changed (expected {spec.license_sha256}, got {actual}). "
            "Re-review the license before updating the manifest."
        )


def select_files(spec: RepoSpec, checkout_dir: Path) -> list[Path]:
    """Deterministic selection: filter by dir, extension and size, then order by path hash.

    Ordering by a hash of the path (rather than alphabetically) spreads the sample
    across the whole tree instead of taking the first directory.
    """
    candidates: set[Path] = set()
    for include in spec.include_dirs:
        root = (checkout_dir / include).resolve()
        for path in root.rglob("*"):
            if ".git" in path.parts or not path.is_file() or path.suffix not in spec.extensions:
                continue
            size = path.stat().st_size
            if spec.min_bytes <= size <= spec.max_bytes:
                candidates.add(path.relative_to(checkout_dir.resolve()))
    ordered = sorted(candidates, key=lambda p: hashlib.sha256(p.as_posix().encode()).hexdigest())
    return ordered[: spec.max_files]


def build_corpus(manifest: Manifest, corpus_dir: Path, work_dir: Path) -> CorpusLock:
    files: list[LockedFile] = []
    for spec in manifest.repos:
        repo_checkout = work_dir / spec.name
        checkout(spec, repo_checkout)
        check_license(spec, repo_checkout)
        out_root = corpus_dir / spec.name
        if out_root.exists():
            shutil.rmtree(out_root)
        for rel in select_files(spec, repo_checkout):
            src = repo_checkout / rel
            dst = out_root / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
            files.append(
                LockedFile(
                    repo=spec.name,
                    language=spec.language,
                    path=rel.as_posix(),
                    sha256=sha256_file(dst),
                    bytes=dst.stat().st_size,
                )
            )
        shutil.copyfile(repo_checkout / spec.license_file, out_root / spec.license_file)
        print(f"{spec.name}: {sum(f.repo == spec.name for f in files)} files", file=sys.stderr)
    return CorpusLock(manifest_sha256=manifest.sha256, files=files)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    settings = get_settings()
    manifest = load_manifest(settings.corpus_manifest)
    with tempfile.TemporaryDirectory() as tmp:
        lock = build_corpus(manifest, settings.corpus_dir, Path(tmp))
    write_lock(lock, settings.corpus_lock)
    print(f"wrote {len(lock.files)} files, corpus sha256 {lock.sha256}", file=sys.stderr)


if __name__ == "__main__":
    main()
