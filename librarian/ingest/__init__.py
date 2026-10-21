"""Corpus ingestion: turn the FastAPI docs and GitHub threads into `Document`s."""

from __future__ import annotations

import logging

from librarian.config import Settings
from librarian.ingest.docs_loader import load_docs
from librarian.ingest.github_loader import load_github
from librarian.models import Document, write_jsonl

log = logging.getLogger(__name__)


def ingest(settings: Settings, docs: bool = True, github: bool = True) -> list[Document]:
    documents: list[Document] = []
    if docs:
        documents += load_docs(settings.fastapi_repo, settings.fastapi_ref, settings.raw_dir)
    if github:
        if settings.github_token:
            documents += load_github(
                settings.fastapi_repo, settings.github_token, settings.raw_dir,
                settings.max_discussions, settings.max_issues, settings.only_answered_discussions,
            )
        else:
            log.warning("GITHUB_TOKEN not set: skipping discussions and issues (docs only)")
    out = settings.processed_dir / "documents.jsonl"
    write_jsonl(out, documents)
    log.info("Wrote %d documents to %s", len(documents), out)
    return documents
