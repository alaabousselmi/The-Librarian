"""Generate an answer from retrieved chunks only, with a citation for every claim."""

from __future__ import annotations

import re
from dataclasses import dataclass

from librarian.llm import LLM, LLMResult
from librarian.retrieval import Hit

IDK = "I don't know based on the FastAPI documentation and discussions I have."

# The fixed part of the prompt comes first and never changes between requests,
# so providers with prompt caching can reuse it (a Week 8 lever).
SYSTEM = f"""You are The Librarian, an assistant that answers questions about the FastAPI web framework.

You are given numbered sources: official FastAPI documentation pages, GitHub Discussions and GitHub issues.

Rules:
1. Answer ONLY from the sources. Do not use outside knowledge, even if you are confident.
2. Cite every factual sentence with the number of the source(s) that support it, like [1] or [2][4].
   Put the citation at the end of the sentence it supports. Never cite a source that does not say it.
3. If the sources do not contain the answer, reply exactly: "{IDK}"
   If they only partly answer it, answer that part and say what is missing.
4. Prefer the official documentation over discussions/issues when they disagree, and say so.
   Discussions and issues describe one user's situation and may be outdated.
5. You may include short code examples, but only code shown in, or directly adapted from, the sources.
6. Be concise: a direct answer first, then details. Use Markdown."""

CITATION = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")
# gpt-oss models sometimes cite in their native style: 【2】 or 【2†L10-L12】
NATIVE_CITATION = re.compile(r"【\s*(\d+(?:\s*,\s*\d+)*)\s*(?:†[^】]*)?】")


def normalize_citations(answer: str) -> str:
    return NATIVE_CITATION.sub(lambda m: f"[{m.group(1)}]", answer)


@dataclass
class Citation:
    n: int
    chunk_id: str
    doc_id: str
    title: str
    url: str
    source_type: str
    snippet: str


@dataclass
class Generation:
    answer: str
    citations: list[Citation]
    abstained: bool
    llm: LLMResult | None
    invalid_citations: list[int]


def format_sources(hits: list[Hit]) -> str:
    blocks = []
    for i, h in enumerate(hits, start=1):
        c = h.chunk
        where = " > ".join(c.heading_path) if c.heading_path else c.title
        meta = c.source_type + (f", {c.created_at[:10]}" if c.created_at else "")
        blocks.append(f"[{i}] ({meta}) {where}\nURL: {c.url}\n{c.text}")
    return "\n\n---\n\n".join(blocks)


def parse_citations(answer: str) -> list[int]:
    nums: list[int] = []
    for m in CITATION.finditer(answer):
        for n in m.group(1).split(","):
            if int(n) not in nums:
                nums.append(int(n))
    return nums


def is_abstention(answer: str) -> bool:
    a = answer.strip().lower()
    return a.startswith("i don't know") or a.startswith("i do not know")


def build_messages(question: str, hits: list[Hit]) -> list[dict]:
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": f"Sources:\n\n{format_sources(hits)}\n\n===\n\nQuestion: {question}"},
    ]


def generate(question: str, hits: list[Hit], llm: LLM, max_tokens: int = 900,
             temperature: float = 0.1) -> Generation:
    if not hits:
        return Generation(IDK, [], True, None, [])
    result = llm.complete(build_messages(question, hits), max_tokens=max_tokens, temperature=temperature)
    answer = normalize_citations(result.text)
    cited = parse_citations(answer)
    valid = [n for n in cited if 1 <= n <= len(hits)]
    invalid = [n for n in cited if n not in valid]
    citations = [
        Citation(n=n, chunk_id=hits[n - 1].chunk.chunk_id, doc_id=hits[n - 1].chunk.doc_id,
                 title=hits[n - 1].chunk.title, url=hits[n - 1].chunk.url,
                 source_type=hits[n - 1].chunk.source_type, snippet=hits[n - 1].chunk.text[:400])
        for n in sorted(valid)
    ]
    return Generation(answer, citations, is_abstention(answer), result, invalid)
