"""Rewrite short, vague or multi-part questions into standalone search queries.

Runs on a small model from a different family than the generator. In ``auto`` mode
a cheap heuristic decides whether a rewrite is worth an LLM call at all; most
well-formed questions skip it (that matters for p95 latency).
"""

from __future__ import annotations

import json
import logging
import re

from librarian.llm import LLM, LLMResult

log = logging.getLogger(__name__)

SYSTEM = """You turn a user's question about the FastAPI Python web framework into search queries
for a documentation search engine (keyword + semantic search).

Rules:
- If the question has several parts, return one query per part (max 3).
- If it is short or vague, expand it into a precise query using FastAPI terminology
  (e.g. "dependency injection", "path operation", "Pydantic model", "background tasks").
- Keep code identifiers exactly as written (e.g. `Depends`, `APIRouter`, `response_model`).
- Do not answer the question.
Return JSON: {"queries": ["...", "..."]}"""

MULTI_PART = re.compile(r"\?.+\?|\b(and also|as well as|additionally)\b|;\s*\w", re.I | re.S)


def needs_rewrite(question: str) -> bool:
    words = question.split()
    return len(words) < 4 or bool(MULTI_PART.search(question))


def rewrite(question: str, llm: LLM, mode: str = "auto") -> tuple[list[str], LLMResult | None]:
    """Return the queries to search with (original question first) and the LLM call, if any."""
    if mode == "never" or (mode == "auto" and not needs_rewrite(question)):
        return [question], None
    try:
        result = llm.complete(
            [{"role": "system", "content": SYSTEM}, {"role": "user", "content": question}],
            max_tokens=300, json_mode=True,
        )
        queries = [q.strip() for q in json.loads(result.text).get("queries", []) if isinstance(q, str) and q.strip()]
    except Exception as exc:  # a failed rewrite must never fail the request
        log.warning("Query rewrite failed, using original question: %s", exc)
        return [question], None
    seen, out = set(), []
    for q in [question, *queries[:3]]:
        if q.lower() not in seen:
            seen.add(q.lower())
            out.append(q)
    return out, result
