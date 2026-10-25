from __future__ import annotations

import os

import pytest

from relay.corpus.store import Corpus, CorpusFile

# boto3 needs credentials to exist even against moto or Floci.
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")


def _code(repo: str, n: int) -> str:
    return "".join(f"def {repo}_fn_{i}(x):\n    return x + {i}\n\n" for i in range(n))


@pytest.fixture
def small_corpus() -> Corpus:
    files = [
        CorpusFile(repo=repo, language="python", path=f"src/mod{i}.py", text=_code(repo, 40 + i))
        for repo in ("alpha", "beta")
        for i in range(4)
    ]
    return Corpus(files, sha256="0" * 64)
