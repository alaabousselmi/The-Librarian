"""Hybrid retrieval: BM25 + dense, fused with Reciprocal Rank Fusion.

The mode can be switched (bm25 | dense | hybrid), which is what the ablation needs.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from librarian.config import RetrievalMode, Settings
from librarian.embeddings import Encoders
from librarian.models import Chunk
from librarian.store import SearchFilters, Store


@dataclass
class Hit:
    chunk: Chunk
    score: float  # fused (RRF) score, or the raw score in single-retriever modes
    scores: dict[str, float] = field(default_factory=dict)


@dataclass
class RetrievalResult:
    hits: list[Hit]
    timings_ms: dict[str, float]
    reranked: bool


def rrf(rankings: list[list[Chunk]], k: int = 60) -> list[tuple[Chunk, float]]:
    """Reciprocal Rank Fusion: score(d) = sum over rankings of 1 / (k + rank)."""
    scores: dict[str, float] = {}
    by_id: dict[str, Chunk] = {}
    for ranking in rankings:
        for rank, chunk in enumerate(ranking, start=1):
            scores[chunk.chunk_id] = scores.get(chunk.chunk_id, 0.0) + 1.0 / (k + rank)
            by_id.setdefault(chunk.chunk_id, chunk)
    return [(by_id[cid], s) for cid, s in sorted(scores.items(), key=lambda kv: kv[1], reverse=True)]


class Retriever:
    def __init__(self, settings: Settings, store: Store, encoders: Encoders):
        self.s = settings
        self.store = store
        self.enc = encoders

    def _first_stage(self, query: str, mode: RetrievalMode, k: int,
                     filters: SearchFilters | None) -> list[tuple[Chunk, float]]:
        if mode == "bm25":
            return self.store.search_bm25(query, k, filters)
        if mode == "dense":
            return self.store.search_dense(query, k, filters)
        bm25 = [c for c, _ in self.store.search_bm25(query, k, filters)]
        dense = [c for c, _ in self.store.search_dense(query, k, filters)]
        return rrf([bm25, dense], self.s.rrf_k)

    def retrieve(self, queries: list[str], *, mode: RetrievalMode | None = None,
                 top_k: int | None = None, filters: SearchFilters | None = None) -> RetrievalResult:
        """Retrieve for one or more (rewritten) queries; results are merged with RRF."""
        mode = mode or self.s.retrieval_mode
        top_k = top_k or self.s.top_k
        timings: dict[str, float] = {}

        t0 = time.perf_counter()
        per_query = [self._first_stage(q, mode, self.s.candidate_k, filters) for q in queries]
        if len(per_query) == 1:
            fused = per_query[0]
        else:
            fused = rrf([[c for c, _ in r] for r in per_query], self.s.rrf_k)
        timings["search_ms"] = (time.perf_counter() - t0) * 1000

        hits = [Hit(c, s, {"first_stage": s}) for c, s in fused]
        return RetrievalResult(hits=hits[:top_k], timings_ms=timings, reranked=False)
