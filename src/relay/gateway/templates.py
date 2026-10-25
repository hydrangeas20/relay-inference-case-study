"""Relay's prompt templates, as they were at the start of the engagement.

`variant="original"` (the default) is Relay's template as shipped: a per-request
header (request ID and timestamp) at the top of every prompt. RLY-4 found that the
header makes every prompt differ from its first tokens, so a prefix cache can't reuse
anything. `variant="metadata"` is the fix: the header leaves the prompt, and the
gateway sends the request ID as request metadata (X-Request-Id) instead.

Why remove rather than move it to the end: for inline completion the prompt ends at the
user's cursor, so text appended after the code would sit between the code and the
completion. Request metadata belongs in the request, not in the model's input.

Keep "original" byte-for-byte unchanged: it's the RLY-4 baseline.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

TemplateVariant = Literal["original", "metadata"]

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
    variant: TemplateVariant = "original",
) -> str:
    header = _header(request_id, now) if variant == "original" else ""
    parts = [header, SYSTEM_PROMPT, f"\nRepository: {repo}\n"]
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
    variant: TemplateVariant = "original",
) -> list[dict[str, str]]:
    header = _header(request_id, now) if variant == "original" else ""
    return [
        {"role": "system", "content": header + SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Repository: {repo}\nFile: {file_path} ({language})\n\n"
                f"```\n{file_content}\n```\n\n{question}"
            ),
        },
    ]
