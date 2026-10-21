"""HTTP service: JSON API + a small web UI for real users."""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from librarian.api.schemas import (
    AskRequest,
    AskResponse,
    CitationOut,
    FeedbackRequest,
    RetrievedOut,
    SearchHit,
)
from librarian.config import RetrievalMode, get_settings
from librarian.store import SearchFilters
from librarian.telemetry import Telemetry

log = logging.getLogger(__name__)
STATIC = Path(__file__).parent / "static"


class RateLimiter:
    """Sliding-window limit per client, protecting the free-tier LLM quota."""

    def __init__(self, per_minute: int):
        self.per_minute = per_minute
        self.hits: dict[str, deque] = defaultdict(deque)
        self.lock = threading.Lock()

    def allow(self, key: str) -> bool:
        if self.per_minute <= 0:
            return True
        now = time.time()
        with self.lock:
            q = self.hits[key]
            while q and now - q[0] > 60:
                q.popleft()
            if len(q) >= self.per_minute:
                return False
            q.append(now)
            return True


def client_key(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "unknown")


def create_app(pipeline=None, telemetry: Telemetry | None = None) -> FastAPI:
    settings = get_settings()
    state: dict = {"pipeline": pipeline, "telemetry": telemetry}

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if state["pipeline"] is None:
            from librarian.pipeline import Pipeline

            state["pipeline"] = Pipeline(settings)
            state["pipeline"].encoders.warmup()
        if state["telemetry"] is None:
            state["telemetry"] = Telemetry(settings.telemetry_db)
        log.info("The Librarian is ready (collection=%s, %d chunks)", settings.collection,
                 state["pipeline"].store.count())
        yield

    app = FastAPI(title="The Librarian", version="0.1.0", lifespan=lifespan,
                  description="Answers FastAPI questions from the docs, Discussions and issues — with citations.")
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins.split(","),
                       allow_methods=["GET", "POST"], allow_headers=["*"])
    limiter = RateLimiter(settings.rate_limit_per_minute)

    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}

    @app.get("/readyz")
    def readyz():
        n = state["pipeline"].store.count()
        if n == 0:
            raise HTTPException(503, "Index is empty: run `librarian build`")
        return {"status": "ready", "chunks": n}

    @app.post("/api/ask", response_model=AskResponse, response_model_exclude_none=True)
    def ask(req: AskRequest, request: Request):
        if not limiter.allow(client_key(request)):
            raise HTTPException(429, "Too many questions — please wait a minute.")
        question = req.question.strip()
        if len(question) > settings.max_question_chars:
            raise HTTPException(422, f"Question is longer than {settings.max_question_chars} characters")
        filters = SearchFilters(**req.filters.model_dump()) if req.filters else None
        pipe = state["pipeline"]
        try:
            result = pipe.ask(question, filters)
        except Exception as exc:
            log.exception("ask failed")
            raise HTTPException(502, "The answer service is temporarily unavailable.") from exc
        state["telemetry"].log_request(result, pipe.generator.model, {
            "mode": settings.retrieval_mode, "rerank": settings.use_reranker, "top_k": settings.top_k,
            "chunking": f"{settings.chunk_strategy}-{settings.chunk_size}-{settings.chunk_overlap}",
        })
        resp = AskResponse(
            request_id=result.request_id,
            answer=result.answer,
            citations=[CitationOut(**c.__dict__) for c in result.citations],
            abstained=result.abstained,
            timings_ms=result.timings_ms,
        )
        if req.debug:
            resp.queries = result.queries
            resp.usage = result.usage
            resp.retrieved = [RetrievedOut(chunk_id=h.chunk.chunk_id, title=h.chunk.title, url=h.chunk.url,
                                           source_type=h.chunk.source_type, score=h.score, scores=h.scores)
                              for h in result.hits]
        return resp

    @app.post("/api/feedback")
    def feedback(req: FeedbackRequest):
        if not state["telemetry"].add_feedback(req.request_id, req.rating, req.comment):
            raise HTTPException(404, "Unknown request_id")
        return {"status": "thanks"}

    @app.get("/api/search", response_model=list[SearchHit])
    def search(q: str = Query(..., min_length=2), mode: RetrievalMode = "hybrid", rerank: bool = True,
               k: int = Query(8, ge=1, le=50)):
        """Retrieval only (no LLM): useful for debugging and for the search-latency metric."""
        res = state["pipeline"].retriever.retrieve([q], mode=mode, rerank=rerank, top_k=k)
        return [SearchHit(chunk_id=h.chunk.chunk_id, title=h.chunk.title, url=h.chunk.url,
                          source_type=h.chunk.source_type, score=h.score, text=h.chunk.text) for h in res.hits]

    @app.get("/api/stats")
    def stats(hours: float | None = None):
        return state["telemetry"].stats(hours * 3600 if hours else None)

    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC / "index.html")

    return app
