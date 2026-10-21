"""Core data types shared by ingestion, indexing, retrieval and generation."""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

SourceType = Literal["docs", "discussion", "issue"]


@dataclass
class Document:
    doc_id: str  # stable across re-ingests, e.g. "docs:tutorial/query-params", "discussion:1234"
    source_type: SourceType
    title: str
    url: str
    text: str  # markdown
    section: str | None = None  # docs top-level folder, or discussion category / issue label
    created_at: str | None = None  # ISO 8601
    updated_at: str | None = None
    author: str | None = None  # role, not a username (see design.md: no personal data)
    extra: dict = field(default_factory=dict)


@dataclass
class Chunk:
    chunk_id: str  # f"{doc_id}#{position}"
    doc_id: str
    source_type: SourceType
    title: str
    url: str  # deep link, with #anchor when the chunk sits under a heading that has one
    heading_path: list[str]
    text: str  # raw chunk text, shown to users and the LLM
    position: int
    n_tokens: int
    section: str | None = None
    created_at: str | None = None
    author: str | None = None

    @property
    def embed_text(self) -> str:
        """Text that gets embedded: a breadcrumb header gives each chunk its context."""
        crumb = " > ".join([self.title, *self.heading_path[1:]]) if self.heading_path else self.title
        return f"{crumb}\n\n{self.text}"

    def to_payload(self) -> dict:
        return asdict(self)

    @classmethod
    def from_payload(cls, payload: dict) -> Chunk:
        return cls(**{k: payload.get(k) for k in cls.__dataclass_fields__})


def write_jsonl(path: Path, rows: Iterable) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(asdict(row) if hasattr(row, "__dataclass_fields__") else row,
                               ensure_ascii=False) + "\n")
            n += 1
    return n


def read_jsonl(path: Path) -> Iterator[dict]:
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def load_documents(path: Path) -> list[Document]:
    return [Document(**row) for row in read_jsonl(path)]
