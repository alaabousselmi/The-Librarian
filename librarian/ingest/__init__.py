"""Corpus ingestion: turn the FastAPI docs into `Document`s."""

from __future__ import annotations

import logging

from librarian.config import Settings
from librarian.ingest.docs_loader import load_docs
from librarian.models import Document, write_jsonl

log = logging.getLogger(__name__)


def ingest(settings: Settings, docs: bool = True) -> list[Document]:
    documents: list[Document] = []
    if docs:
        documents += load_docs(settings.fastapi_repo, settings.fastapi_ref, settings.raw_dir)
    out = settings.processed_dir / "documents.jsonl"
    write_jsonl(out, documents)
    log.info("Wrote %d documents to %s", len(documents), out)
    return documents
