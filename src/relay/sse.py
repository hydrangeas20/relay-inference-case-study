"""Parsing of OpenAI-style Server-Sent Event lines, shared by the gateway and load generator."""

from __future__ import annotations

import json


def chunk_content(line: str) -> str | None:
    """Generated output carried by one SSE line, or None if the line carries none.

    Handles completions (`choices[].text`), chat (`choices[].delta.content`) and
    tool calls (`choices[].delta.tool_calls[].function.arguments`, or the call's
    name when arguments haven't started yet).
    """
    if not line.startswith("data:"):
        return None
    data = line[5:].strip()
    if not data or data == "[DONE]":
        return None
    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        return None
    parts: list[str] = []
    for choice in payload.get("choices") or []:
        if choice.get("text"):
            parts.append(choice["text"])
        delta = choice.get("delta") or {}
        if delta.get("content"):
            parts.append(delta["content"])
        for call in delta.get("tool_calls") or []:
            fn = call.get("function") or {}
            parts.append(fn.get("arguments") or fn.get("name") or "")
    text = "".join(parts)
    return text or None
