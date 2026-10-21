"""The online path: rewrite -> retrieve (hybrid) -> rerank -> abstain? -> generate."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field

from librarian.config import RetrievalMode, Settings, get_settings
from librarian.embeddings import Encoders
from librarian.generate import IDK, Citation, generate
from librarian.llm import LLM
from librarian.retrieval import Hit, Retriever
from librarian.rewrite import rewrite
from librarian.store import SearchFilters, Store


@dataclass
class AskOptions:
    """Per-request overrides, used by the eval/ablation scripts and the debug API."""

    mode: RetrievalMode | None = None
    rerank: bool | None = None
    top_k: int | None = None
    rewrite_mode: str | None = None
    abstain_threshold: float | None = None


@dataclass
class AskResult:
    request_id: str
    question: str
    answer: str
    citations: list[Citation]
    abstained: bool
    abstain_reason: str | None
    queries: list[str]
    hits: list[Hit]
    timings_ms: dict[str, float]
    usage: dict[str, float] = field(default_factory=dict)


class Pipeline:
    def __init__(self, settings: Settings | None = None, store: Store | None = None):
        self.s = settings or get_settings()
        self.encoders = store.enc if store else Encoders(self.s)
        self.store = store or Store(self.s, self.encoders)
        self.retriever = Retriever(self.s, self.store, self.encoders)
        self.generator = LLM("generator", self.s)
        self.rewriter = LLM("rewriter", self.s)

    def ask(self, question: str, filters: SearchFilters | None = None,
            options: AskOptions | None = None) -> AskResult:
        o = options or AskOptions()
        t_start = time.perf_counter()
        timings: dict[str, float] = {}
        usage = {"input_tokens": 0, "output_tokens": 0, "cached_tokens": 0, "cost_usd": 0.0, "llm_calls": 0}

        def account(r):
            if r is not None:
                usage["input_tokens"] += r.input_tokens
                usage["output_tokens"] += r.output_tokens
                usage["cached_tokens"] += r.cached_tokens
                usage["cost_usd"] += r.cost_usd
                usage["llm_calls"] += 1

        t = time.perf_counter()
        queries, rw = rewrite(question, self.rewriter, o.rewrite_mode or self.s.rewrite_mode)
        account(rw)
        timings["rewrite_ms"] = (time.perf_counter() - t) * 1000

        retrieval = self.retriever.retrieve(queries, mode=o.mode, rerank=o.rerank, top_k=o.top_k,
                                            filters=filters, rerank_query=question)
        timings.update(retrieval.timings_ms)
        hits = retrieval.hits

        threshold = self.s.abstain_threshold if o.abstain_threshold is None else o.abstain_threshold
        abstain_reason = None
        if not hits:
            abstain_reason = "no_results"
        elif retrieval.reranked and hits[0].score < threshold:
            abstain_reason = "low_relevance"

        if abstain_reason:
            answer, citations, abstained = IDK, [], True
            timings["generate_ms"] = 0.0
        else:
            t = time.perf_counter()
            gen = generate(question, hits, self.generator, self.s.generator_max_tokens,
                           self.s.generator_temperature)
            timings["generate_ms"] = (time.perf_counter() - t) * 1000
            account(gen.llm)
            answer, citations, abstained = gen.answer, gen.citations, gen.abstained
            if abstained:
                abstain_reason = "model"

        timings["total_ms"] = (time.perf_counter() - t_start) * 1000
        return AskResult(
            request_id=uuid.uuid4().hex,
            question=question,
            answer=answer,
            citations=citations,
            abstained=abstained,
            abstain_reason=abstain_reason,
            queries=queries,
            hits=hits,
            timings_ms={k: round(v, 1) for k, v in timings.items()},
            usage=usage,
        )
