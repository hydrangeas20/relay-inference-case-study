"""Download Azure's 2024 code trace and verify its SHA-256.

Usage: uv run python analysis/azure_download.py
"""

from __future__ import annotations

import subprocess

import common


def main() -> None:
    path = common.RAW_PATH
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["curl", "-sSL", "--fail", "-o", str(path), common.RAW_URL], check=True)
    common.verify_raw(path)
    print(f"{path}: SHA-256 verified ({common.RAW_SHA256})")


if __name__ == "__main__":
    main()
