"""Relay's prompt templates, as they were at the start of the engagement.

These are deliberately left as Relay wrote them. The per-request header at the top
of every prompt is investigated in RLY-4; don't "fix" it outside that ticket, or
the RLY-4 before/after comparison loses its baseline.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

SYSTEM_PROMPT = """You are Relay, an AI coding assistant embedded in the user's editor.
Follow the conventions of the surrounding code. Prefer small, correct changes.
Never invent APIs that are not visible in the provided context.
When completing code, output only the code that belongs at the cursor.
When answering questions, be concise and reference specific functions or lines."""

AGENT_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_repo",
            "description": "Search the user's repository for a string or symbol.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file from the user's repository.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_tests",
            "description": "Run the test suite, optionally filtered to a path.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": [],
            },
        },
    },
]


def _header(request_id: str, now: datetime | None = None) -> str:
    ts = (now or datetime.now(UTC)).isoformat(timespec="milliseconds")
    return f"[relay request_id={request_id} ts={ts}]\n"


def completion_prompt(
    *,
    request_id: str,
    repo: str,
    file_path: str,
    language: str,
    prefix: str,
    context_files: list[tuple[str, str]],
    now: datetime | None = None,
) -> str:
    parts = [_header(request_id, now), SYSTEM_PROMPT, f"\nRepository: {repo}\n"]
    for path, content in context_files:
        parts.append(f"\n--- {path} ---\n{content}\n")
    parts.append(f"\n--- {file_path} ({language}) ---\n{prefix}")
    return "".join(parts)


def agent_messages(
    *,
    request_id: str,
    repo: str,
    file_path: str,
    language: str,
    file_content: str,
    question: str,
    now: datetime | None = None,
) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": _header(request_id, now) + SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Repository: {repo}\nFile: {file_path} ({language})\n\n"
                f"```\n{file_content}\n```\n\n{question}"
            ),
        },
    ]
