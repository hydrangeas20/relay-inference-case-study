"""Load the local corpus, verifying every file against the lock."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from relay.corpus.manifest import CorpusLock


class CorpusIntegrityError(RuntimeError):
    pass


@dataclass(frozen=True)
class CorpusFile:
    repo: str
    language: str
    path: str
    text: str


class Corpus:
    def __init__(self, files: list[CorpusFile], sha256: str) -> None:
        if not files:
            raise CorpusIntegrityError("corpus is empty; run `make corpus` first")
        self.files = files
        self.sha256 = sha256
        self._by_key = {(f.repo, f.path): f for f in files}

    def get(self, repo: str, path: str) -> CorpusFile:
        try:
            return self._by_key[(repo, path)]
        except KeyError as exc:
            raise CorpusIntegrityError(f"{repo}/{path} is not in the corpus") from exc

    def repos(self) -> list[str]:
        return sorted({f.repo for f in self.files})


def load_corpus(lock: CorpusLock, corpus_dir: Path) -> Corpus:
    files: list[CorpusFile] = []
    for entry in lock.files:
        path = corpus_dir / entry.repo / entry.path
        if not path.is_file():
            raise CorpusIntegrityError(f"missing corpus file {path}; run `make corpus`")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != entry.sha256:
            raise CorpusIntegrityError(f"{path} does not match the corpus lock")
        files.append(
            CorpusFile(
                repo=entry.repo,
                language=entry.language,
                path=entry.path,
                text=raw.decode("utf-8", errors="replace"),
            )
        )
    return Corpus(files, lock.sha256)
