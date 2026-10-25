"""The pinned list of source repositories (corpus/repos.toml) and the corpus lock file."""

from __future__ import annotations

import hashlib
import json
import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

AllowedLicense = Literal["MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause"]


class RepoSpec(BaseModel):
    name: str
    url: str
    commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    language: str
    extensions: list[str]
    include_dirs: list[str]
    license: AllowedLicense
    license_file: str
    license_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    max_files: int
    min_bytes: int
    max_bytes: int


class Manifest(BaseModel):
    repos: list[RepoSpec]
    sha256: str


def load_manifest(path: Path) -> Manifest:
    raw = path.read_bytes()
    data = tomllib.loads(raw.decode())
    defaults = data.get("defaults", {})
    repos = [RepoSpec(**{**defaults, **repo}) for repo in data["repo"]]
    names = [r.name for r in repos]
    if len(names) != len(set(names)):
        raise ValueError("repo names in the corpus manifest must be unique")
    return Manifest(repos=repos, sha256=hashlib.sha256(raw).hexdigest())


class LockedFile(BaseModel):
    repo: str
    language: str
    path: str
    sha256: str
    bytes: int


class CorpusLock(BaseModel):
    manifest_sha256: str
    files: list[LockedFile]

    @property
    def sha256(self) -> str:
        """Identifies the exact corpus contents; recorded in every trace."""
        payload = json.dumps(self.model_dump(), sort_keys=True).encode()
        return hashlib.sha256(payload).hexdigest()


def load_lock(path: Path) -> CorpusLock:
    return CorpusLock.model_validate_json(path.read_text())


def write_lock(lock: CorpusLock, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(lock.model_dump(), indent=2) + "\n")
