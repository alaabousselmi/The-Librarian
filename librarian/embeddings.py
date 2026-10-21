"""Dense (bge-small) and sparse (BM25) encoders, plus the cross-encoder reranker.

All three run locally on CPU through fastembed/ONNX: zero API cost, no torch,
and a Docker image small enough for free hosting. Models are loaded lazily and
cached on disk (MODEL_CACHE_DIR) so the container can pre-download them at build.
"""

from __future__ import annotations

from functools import cached_property

from qdrant_client import models

from librarian.config import Settings


class Encoders:
    def __init__(self, settings: Settings):
        self.s = settings

    @cached_property
    def dense(self):
        from fastembed import TextEmbedding

        return TextEmbedding(self.s.dense_model, cache_dir=self.s.model_cache_dir)

    @cached_property
    def sparse(self):
        from fastembed import SparseTextEmbedding

        return SparseTextEmbedding(self.s.sparse_model, cache_dir=self.s.model_cache_dir)

    @cached_property
    def reranker(self):
        from fastembed.rerank.cross_encoder import TextCrossEncoder

        return TextCrossEncoder(self.s.rerank_model, cache_dir=self.s.model_cache_dir)

    @cached_property
    def dense_dim(self) -> int:
        return len(self.embed_query("dimension probe"))

    def embed_documents(self, texts: list[str], batch_size: int = 64) -> list[list[float]]:
        return [v.tolist() for v in self.dense.embed(texts, batch_size=batch_size)]

    def embed_query(self, text: str) -> list[float]:
        return next(iter(self.dense.embed([self.s.query_prefix + text]))).tolist()

    def sparse_documents(self, texts: list[str], batch_size: int = 256) -> list[models.SparseVector]:
        return [models.SparseVector(indices=v.indices.tolist(), values=v.values.tolist())
                for v in self.sparse.embed(texts, batch_size=batch_size)]

    def sparse_query(self, text: str) -> models.SparseVector:
        v = next(iter(self.sparse.query_embed(text)))
        return models.SparseVector(indices=v.indices.tolist(), values=v.values.tolist())

    def rerank(self, query: str, texts: list[str]) -> list[float]:
        return [float(s) for s in self.reranker.rerank(query, texts)]

    def warmup(self) -> None:
        self.embed_query("warmup")
        self.sparse_query("warmup")
        self.rerank("warmup", ["warmup"])
