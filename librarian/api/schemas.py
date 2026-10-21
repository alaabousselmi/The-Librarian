from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Filters(BaseModel):
    source_types: list[Literal["docs", "discussion", "issue"]] | None = None
    sections: list[str] | None = None
    date_from: str | None = Field(None, description="ISO date, e.g. 2023-01-01")
    date_to: str | None = None


class AskRequest(BaseModel):
    question: str = Field(..., min_length=3)
    filters: Filters | None = None
    debug: bool = False


class CitationOut(BaseModel):
    n: int
    title: str
    url: str
    source_type: str
    snippet: str
    chunk_id: str


class RetrievedOut(BaseModel):
    chunk_id: str
    title: str
    url: str
    source_type: str
    score: float
    scores: dict[str, float]


class AskResponse(BaseModel):
    request_id: str
    answer: str
    citations: list[CitationOut]
    abstained: bool
    timings_ms: dict[str, float]
    queries: list[str] | None = None
    retrieved: list[RetrievedOut] | None = None
    usage: dict[str, float] | None = None


class FeedbackRequest(BaseModel):
    request_id: str
    rating: Literal[1, -1]
    comment: str | None = Field(None, max_length=2000)


class SearchHit(BaseModel):
    chunk_id: str
    title: str
    url: str
    source_type: str
    score: float
    text: str
