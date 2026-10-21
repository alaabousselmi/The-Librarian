"""Split documents into chunks.

Two strategies, so chunking is an experiment and not a default (see eval/ablation.py):

* ``markdown`` — structure-aware. Never splits inside a fenced code block unless the
  block alone exceeds the budget; starts a new chunk at every H1–H3; overlaps by
  whole trailing blocks; records the heading path and the section anchor so each
  chunk can be cited with a deep link.
* ``fixed`` — the naive baseline: a sliding window of N tokens over the raw text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache

import tiktoken

from librarian.models import Chunk, Document

HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*(?:\{\s*#(?P<anchor>[\w\-]+)\s*\})?\s*$")
SECTION_BREAK_LEVEL = 3  # headings at this level or above start a new chunk


@lru_cache
def _encoder():
    return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    return len(_encoder().encode(text, disallowed_special=()))


@dataclass
class Block:
    kind: str  # "heading" | "code" | "text"
    text: str
    level: int = 0
    title: str = ""
    anchor: str | None = None
    tokens: int = 0


def parse_blocks(markdown: str) -> list[Block]:
    blocks: list[Block] = []
    buf: list[str] = []
    fence: list[str] | None = None

    def flush_text():
        if any(line.strip() for line in buf):
            blocks.append(Block("text", "\n".join(buf).strip()))
        buf.clear()

    for line in markdown.splitlines():
        if fence is not None:
            fence.append(line)
            if line.strip().startswith("```"):
                blocks.append(Block("code", "\n".join(fence)))
                fence = None
            continue
        if line.strip().startswith("```"):
            flush_text()
            fence = [line]
            continue
        if m := HEADING.match(line):
            flush_text()
            title = m.group(2).strip()
            blocks.append(Block("heading", f"{m.group(1)} {title}", level=len(m.group(1)),
                                title=title, anchor=m.group("anchor")))
            continue
        if not line.strip():
            flush_text()
        else:
            buf.append(line)
    if fence is not None:  # unterminated fence: keep the content anyway
        blocks.append(Block("code", "\n".join(fence) + "\n```"))
    flush_text()
    for b in blocks:
        b.tokens = count_tokens(b.text)
    return blocks


def _truncate_line(line: str, max_tokens: int) -> str:
    """Single huge lines in code (base64 images, minified data) carry no searchable meaning."""
    ids = _encoder().encode(line, disallowed_special=())
    if len(ids) <= max_tokens:
        return line
    return _encoder().decode(ids[:max_tokens]) + " ...[truncated]"


def _split_oversized(block: Block, budget: int) -> list[Block]:
    """Split a single block that is bigger than the whole budget."""
    if block.tokens <= budget:
        return [block]
    if block.kind == "code":
        lines = block.text.splitlines()
        opener, body = lines[0], [_truncate_line(line, budget // 4) for line in lines[1:-1]]
        pieces, cur = [], []
        for line in body:
            if cur and count_tokens("\n".join([opener, *cur, line, "```"])) > budget:
                pieces.append(cur)
                cur = []
            cur.append(line)
        if cur:
            pieces.append(cur)
        return [Block("code", "\n".join([opener, *p, "```"]), tokens=count_tokens("\n".join([opener, *p, "```"])))
                for p in pieces]
    # text: split on sentence boundaries, falling back to raw token windows
    sentences = re.split(r"(?<=[.!?])\s+", block.text)
    out, cur = [], ""
    for s in sentences:
        cand = f"{cur} {s}".strip()
        if cur and count_tokens(cand) > budget:
            out.append(cur)
            cur = s
        else:
            cur = cand
    if cur:
        out.append(cur)
    result = []
    enc = _encoder()
    for piece in out:
        ids = enc.encode(piece, disallowed_special=())
        for i in range(0, len(ids), budget):
            text = enc.decode(ids[i : i + budget])
            result.append(Block("text", text, tokens=count_tokens(text)))
    return result


@dataclass
class _Draft:
    blocks: list[Block] = field(default_factory=list)
    heading_path: list[str] = field(default_factory=list)
    anchor: str | None = None

    @property
    def tokens(self) -> int:
        return sum(b.tokens for b in self.blocks) + max(len(self.blocks) - 1, 0)

    def has_body(self) -> bool:
        return any(b.kind != "heading" for b in self.blocks)


def _make_chunk(doc: Document, draft: _Draft, position: int) -> Chunk:
    text = "\n\n".join(b.text for b in draft.blocks)
    url = doc.url
    if draft.anchor and doc.source_type == "docs":
        url = f"{doc.url}#{draft.anchor}"
    return Chunk(
        chunk_id=f"{doc.doc_id}#{position}",
        doc_id=doc.doc_id,
        source_type=doc.source_type,
        title=doc.title,
        url=url,
        heading_path=list(draft.heading_path) or [doc.title],
        text=text,
        position=position,
        n_tokens=count_tokens(text),
        section=doc.section,
        created_at=doc.created_at,
        author=doc.author,
    )


def chunk_markdown(doc: Document, size: int, overlap: int) -> list[Chunk]:
    chunks: list[Chunk] = []
    path: dict[int, str] = {}
    anchor: str | None = None
    draft = _Draft()

    def current_path() -> list[str]:
        return [path[k] for k in sorted(path)]

    def emit(carry_overlap: bool):
        nonlocal draft
        if not draft.has_body():
            return
        chunks.append(_make_chunk(doc, draft, len(chunks)))
        carried: list[Block] = []
        if carry_overlap and overlap > 0:
            budget = overlap
            for b in reversed(draft.blocks):
                if b.kind == "heading" or b.tokens > budget:
                    break
                carried.insert(0, b)
                budget -= b.tokens
        draft = _Draft(blocks=carried, heading_path=current_path(), anchor=anchor)

    for block in parse_blocks(doc.text):
        if block.kind == "heading":
            if block.level <= SECTION_BREAK_LEVEL:
                emit(carry_overlap=False)
            path = {k: v for k, v in path.items() if k < block.level}
            path[block.level] = block.title
            if block.anchor:
                anchor = block.anchor
            if not draft.has_body():
                draft.heading_path, draft.anchor = current_path(), anchor
            draft.blocks.append(block)
            continue
        for piece in _split_oversized(block, size):
            if draft.has_body() and draft.tokens + piece.tokens > size:
                emit(carry_overlap=True)
                # the carried overlap must not push the new chunk over budget
                while draft.blocks and draft.tokens + piece.tokens > size:
                    draft.blocks.pop(0)
            draft.blocks.append(piece)
    emit(carry_overlap=False)
    return chunks


def chunk_fixed(doc: Document, size: int, overlap: int) -> list[Chunk]:
    enc = _encoder()
    ids = enc.encode(doc.text, disallowed_special=())
    step = max(size - overlap, 1)
    chunks = []
    for start in range(0, max(len(ids), 1), step):
        draft = _Draft(blocks=[Block("text", enc.decode(ids[start : start + size]))], heading_path=[doc.title])
        draft.blocks[0].tokens = len(ids[start : start + size])
        chunks.append(_make_chunk(doc, draft, len(chunks)))
        if start + size >= len(ids):
            break
    return chunks


def chunk_documents(docs: list[Document], strategy: str, size: int, overlap: int) -> list[Chunk]:
    fn = chunk_markdown if strategy == "markdown" else chunk_fixed
    return [c for d in docs for c in fn(d, size, overlap)]
