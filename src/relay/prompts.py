"""Turn trace requests into the payloads Relay's editor clients send to the gateway.

This is the client side: it decides *what the user's editor sends* (code around
the cursor, neighbouring files, a question). How that becomes a model prompt is
Relay's server-side concern and lives in relay.gateway.templates.
"""

from __future__ import annotations

from typing import Any

from relay.corpus.store import Corpus
from relay.traces.schema import AgentRequest, CompletionRequest, IndexingRequest

AGENT_QUESTIONS = [
    "What does this file do? Summarize its main responsibilities.",
    "Find any functions in this file that lack error handling and explain the risk.",
    "Where is this module's main entry point, and what calls it?",
    "Suggest a unit test for the most complex function in this file.",
    "Are there any obvious performance problems in this code?",
    "Explain the data flow through this file step by step.",
    "Which parts of this file would be hardest to change safely, and why?",
    "Search the repo for other callers of the main function here and list them.",
]

CONTEXT_FILE_CHARS = 1_500  # chars of each neighbouring file the editor sends


def completion_payload(req: CompletionRequest, corpus: Corpus) -> dict[str, Any]:
    f = corpus.get(req.file.repo, req.file.path)
    start = max(0, req.cursor - req.prefix_chars)
    return {
        "request_id": req.req_id,
        "repo": f.repo,
        "file_path": f.path,
        "language": f.language,
        "prefix": f.text[start : req.cursor],
        "suffix": f.text[req.cursor : req.cursor + req.suffix_chars],
        "context_files": [
            {"path": c.path, "content": corpus.get(c.repo, c.path).text[:CONTEXT_FILE_CHARS]}
            for c in req.context_files
        ],
        "max_tokens": req.max_tokens,
    }


def agent_payload(req: AgentRequest, corpus: Corpus) -> dict[str, Any]:
    f = corpus.get(req.file.repo, req.file.path)
    return {
        "request_id": req.req_id,
        "repo": f.repo,
        "file_path": f.path,
        "language": f.language,
        "file_content": f.text[: req.context_chars],
        "question": AGENT_QUESTIONS[req.question_id],
        "max_tokens": req.max_tokens,
    }


def indexing_job(req: IndexingRequest, corpus: Corpus) -> dict[str, Any]:
    chunks: list[str] = []
    for ref in req.files:
        text = corpus.get(ref.repo, ref.path).text
        chunks += [text[i : i + req.chunk_chars] for i in range(0, len(text), req.chunk_chars)]
    return {
        "job_id": req.req_id,
        "repo": req.files[0].repo,
        "paths": [r.path for r in req.files],
        "chunks": chunks,
    }
