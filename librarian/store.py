"""Qdrant index: one collection holding a dense vector and a BM25 sparse vector per chunk.

Why Qdrant (full argument in docs/design.md):
  * dense + sparse (BM25 with server-side IDF) in a single store, so hybrid search
    needs no second system to keep in sync;
  * payload filters on source_type / section / created_at for metadata filtering;
  * the same client runs embedded (local file, zero setup for dev and CI), as a
    Docker service, or on Qdrant Cloud's free tier for the deployed service.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from qdrant_client import QdrantClient, models

from librarian.config import Settings
from librarian.embeddings import Encoders
from librarian.models import Chunk

log = logging.getLogger(__name__)

DENSE, SPARSE = "dense", "bm25"


@dataclass
class SearchFilters:
    source_types: list[str] | None = None
    sections: list[str] | None = None
    date_from: str | None = None  # ISO date, applies to discussions/issues
    date_to: str | None = None

    def to_qdrant(self) -> models.Filter | None:
        must: list[models.Condition] = []
        if self.source_types:
            must.append(models.FieldCondition(key="source_type", match=models.MatchAny(any=self.source_types)))
        if self.sections:
            must.append(models.FieldCondition(key="section", match=models.MatchAny(any=self.sections)))
        if self.date_from or self.date_to:
            must.append(models.FieldCondition(
                key="created_at", range=models.DatetimeRange(gte=self.date_from, lte=self.date_to)))
        return models.Filter(must=must) if must else None


def make_client(settings: Settings) -> QdrantClient:
    if settings.qdrant_url:
        return QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key or None, timeout=30)
    return QdrantClient(path=settings.qdrant_path)


def point_id(chunk_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))


class Store:
    def __init__(self, settings: Settings, encoders: Encoders, client: QdrantClient | None = None,
                 collection: str | None = None):
        self.s = settings
        self.enc = encoders
        self.client = client or make_client(settings)
        self.collection = collection or settings.collection

    # ---------- indexing ----------
    def recreate(self) -> None:
        if self.client.collection_exists(self.collection):
            self.client.delete_collection(self.collection)
        self.client.create_collection(
            self.collection,
            vectors_config={DENSE: models.VectorParams(size=self.enc.dense_dim, distance=models.Distance.COSINE)},
            sparse_vectors_config={SPARSE: models.SparseVectorParams(modifier=models.Modifier.IDF)},
        )
        # Embedded mode on Windows can resurrect old points after delete+create (the
        # storage file is still open); make "recreate" really mean empty.
        if self.count():
            self.client.delete(self.collection, points_selector=models.FilterSelector(filter=models.Filter()))
        if self.s.qdrant_url:  # payload indexes are a server feature (no-ops in embedded mode)
            for key, schema in [("source_type", models.PayloadSchemaType.KEYWORD),
                                ("section", models.PayloadSchemaType.KEYWORD),
                                ("doc_id", models.PayloadSchemaType.KEYWORD),
                                ("created_at", models.PayloadSchemaType.DATETIME)]:
                self.client.create_payload_index(self.collection, key, field_schema=schema)

    def upsert(self, chunks: list[Chunk], batch_size: int = 128) -> None:
        # Encoder batches are padded to their longest text: grouping chunks of similar length
        # cut indexing time ~3x (mean chunk is ~110 tokens, the longest ~400).
        chunks = sorted(chunks, key=lambda c: c.n_tokens)
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i : i + batch_size]
            texts = [c.embed_text for c in batch]
            dense = self.enc.embed_documents(texts)
            sparse = self.enc.sparse_documents(texts)
            self.client.upsert(self.collection, points=[
                models.PointStruct(id=point_id(c.chunk_id), vector={DENSE: d, SPARSE: s}, payload=c.to_payload())
                for c, d, s in zip(batch, dense, sparse, strict=True)
            ])
            log.info("Indexed %d/%d chunks", min(i + batch_size, len(chunks)), len(chunks))

    def count(self) -> int:
        if not self.client.collection_exists(self.collection):
            return 0
        return self.client.count(self.collection, exact=True).count

    # ---------- search ----------
    def _query(self, query, using: str, k: int, filters: SearchFilters | None) -> list[tuple[Chunk, float]]:
        res = self.client.query_points(
            self.collection, query=query, using=using, limit=k, with_payload=True,
            query_filter=filters.to_qdrant() if filters else None,
        )
        return [(Chunk.from_payload(p.payload), p.score) for p in res.points]

    def search_dense(self, query: str, k: int, filters: SearchFilters | None = None):
        return self._query(self.enc.embed_query(query), DENSE, k, filters)

    def search_bm25(self, query: str, k: int, filters: SearchFilters | None = None):
        return self._query(self.enc.sparse_query(query), SPARSE, k, filters)
