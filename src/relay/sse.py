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


def chunk_timings(line: str) -> dict[str, float] | None:
    """Backend-reported timings carried by an SSE line, if the server sends them.

    llama.cpp's server adds a `timings` object to its final chunk (cache_n: prompt tokens
    reused from the KV cache; prompt_n: prompt tokens evaluated; prompt_ms, predicted_n,
    predicted_ms). vLLM and the simulator don't, so this returns None for them.
    """
    if not line.startswith("data:"):
        return None
    data = line[5:].strip()
    if not data or data == "[DONE]" or '"timings"' not in data:
        return None
    try:
        timings = json.loads(data).get("timings")
    except (json.JSONDecodeError, AttributeError):
        return None
    if not isinstance(timings, dict):
        return None
    return {
        k: float(v)
        for k, v in timings.items()
        if isinstance(v, int | float) and not isinstance(v, bool)
    }
