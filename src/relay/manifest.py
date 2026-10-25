"""Run manifest: everything needed to say where a result came from (methodology rule 1).

Every summary carries one. It records the code (git commit, dirty tree), the
environment (Python, key packages, host CPU and memory), what the gateway was actually
configured to do (asked from the gateway, not assumed), and what the inference server
says about itself. Fields that can't be read are recorded as null with a reason, never
guessed.
"""

from __future__ import annotations

import hashlib
import os
import platform
import subprocess
from importlib import metadata
from pathlib import Path
from typing import Any

import httpx

PACKAGES = ("relay", "fastapi", "httpx", "uvicorn", "numpy", "pydantic", "boto3")


def _git(*args: str) -> str | None:
    try:
        out = subprocess.run(["git", *args], capture_output=True, text=True, check=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip()


def git_info() -> dict[str, Any]:
    status = _git("status", "--porcelain", "--untracked-files=no")
    return {
        "commit": _git("rev-parse", "HEAD"),
        "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        "dirty": None if status is None else bool(status),
    }


def _cpu_model() -> str | None:
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        return None
    return None


def _mem_total_gb() -> float | None:
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                return round(int(line.split()[1]) / 1024**2, 1)
    except (OSError, ValueError):
        return None
    return None


def environment() -> dict[str, Any]:
    versions: dict[str, str | None] = {}
    for name in PACKAGES:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = None
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "cpu_model": _cpu_model(),
        "logical_cpus": os.cpu_count(),
        "mem_total_gb": _mem_total_gb(),
        "packages": versions,
    }


async def _get_json(http: httpx.AsyncClient, url: str) -> dict[str, Any] | None:
    try:
        resp = await http.get(url, timeout=5.0)
        resp.raise_for_status()
        body = resp.json()
    except (httpx.HTTPError, ValueError):
        return None
    return body if isinstance(body, dict) else None


def _sha256(path: Path) -> str | None:
    try:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for block in iter(lambda: f.read(1 << 20), b""):
                h.update(block)
        return h.hexdigest()
    except OSError:
        return None


async def inference_server(http: httpx.AsyncClient, base_url: str) -> dict[str, Any]:
    """What the OpenAI-compatible server reports: /v1/models everywhere, plus llama.cpp's
    /props (build, model file, context size, slots) when the server is llama.cpp."""
    root = base_url.rstrip("/").removesuffix("/v1")
    models = await _get_json(http, f"{base_url.rstrip('/')}/models")
    props = await _get_json(http, f"{root}/props")
    info: dict[str, Any] = {"base_url": base_url, "models": models}
    if props is not None:
        settings = props.get("default_generation_settings") or {}
        model_path = props.get("model_path")
        info["engine"] = "llama.cpp"
        info["llama_cpp"] = {
            "build_info": props.get("build_info"),
            "model_path": model_path,
            # Only computable when the server runs on this host.
            "model_sha256": _sha256(Path(model_path)) if model_path else None,
            "total_slots": props.get("total_slots"),
            "n_ctx": settings.get("n_ctx"),
        }
    return info


async def collect(
    http: httpx.AsyncClient, gateway_url: str, inference_base_url: str
) -> dict[str, Any]:
    return {
        "git": git_info(),
        "environment": environment(),
        "gateway": await _get_json(http, f"{gateway_url.rstrip('/')}/info"),
        "inference_server": await inference_server(http, inference_base_url),
    }
