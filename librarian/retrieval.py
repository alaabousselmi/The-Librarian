"""Hybrid retrieval: BM25 + dense, fused with Reciprocal Rank Fusion, then reranked.

Every stage can be switched off, which is exactly what the ablation needs:
  bm25 | dense | hybrid   x   reranker on/off.
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
    score: float  # final ordering score (rerank logit if reranked, else fused/raw score)
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
                 rerank: bool | None = None, top_k: int | None = None,
                 filters: SearchFilters | None = None, rerank_query: str | None = None) -> RetrievalResult:
        """Retrieve for one or more (rewritten) queries; results are merged with RRF."""
        mode = mode or self.s.retrieval_mode
        rerank = self.s.use_reranker if rerank is None else rerank
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
        if rerank and hits:
            t1 = time.perf_counter()
            if len(queries) > 1:
                hits = self._rerank_per_subquery(queries[1:], per_query, top_k)
            else:
                hits = self._rerank(rerank_query or queries[0], hits[: self.s.rerank_candidates])
            timings["rerank_ms"] = (time.perf_counter() - t1) * 1000

        return RetrievalResult(hits=hits[:top_k], timings_ms=timings, reranked=rerank)

    def _rerank(self, query: str, candidates: list[Hit]) -> list[Hit]:
        logits = self.enc.rerank(query, [h.chunk.embed_text for h in candidates])
        for h, logit in zip(candidates, logits, strict=True):
            h.scores["rerank"] = logit
            h.score = logit
        return sorted(candidates, key=lambda h: h.score, reverse=True)

    def _rerank_per_subquery(self, subqueries: list[str], per_query: list[list[tuple[Chunk, float]]],
                             top_k: int) -> list[Hit]:
        """Multi-part questions: rerank each part against its own candidates, then interleave.

        Reranking everything against the full multi-part question lets the dominant part take
        every slot (observed: "enable CORS? and how to test?" returned only CORS chunks).
        """
        n_cand = max(self.s.rerank_candidates // len(subqueries), top_k)
        ranked = [self._rerank(q, [Hit(c, s, {"first_stage": s}) for c, s in res[:n_cand]])
                  for q, res in zip(subqueries, per_query[1:], strict=True)]
        merged: list[Hit] = []
        seen: set[str] = set()
        for i in range(max(len(r) for r in ranked)):
            for r in ranked:
                if i < len(r) and r[i].chunk.chunk_id not in seen:
                    seen.add(r[i].chunk.chunk_id)
                    merged.append(r[i])
        # best score first so the abstention check sees the most relevant chunk
        head = sorted(merged[:top_k], key=lambda h: h.score, reverse=True)
        return head + merged[top_k:]
