"""All runtime configuration, loaded from environment variables / .env.

Every tunable that the eval or the Week 8 optimisation might touch lives here,
so experiments are config changes, not code changes.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent
# Source checkout: <repo>/data. Installed package (Docker): set DATA_DIR, since ROOT is site-packages.
DATA_DIR = Path(os.environ.get("DATA_DIR", ROOT / "data"))

RetrievalMode = Literal["bm25", "dense", "hybrid"]
LLMRole = Literal["generator", "rewriter", "judge"]


@dataclass(frozen=True)
class RoleConfig:
    model: str
    base_url: str
    api_key: str
    extra_body: dict = field(default_factory=dict)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    # --- LLMs: shared endpoint, per-role model and optional overrides ---
    llm_base_url: str = "https://api.groq.com/openai/v1"
    llm_api_key: str = ""
    llm_timeout_s: float = 60.0
    llm_max_retries: int = 4

    generator_model: str = "openai/gpt-oss-120b"
    generator_base_url: str = ""
    generator_api_key: str = ""
    generator_extra_body: str = '{"reasoning_effort": "low"}'
    generator_max_tokens: int = 900
    generator_temperature: float = 0.1

    rewriter_model: str = "allam-2-7b"
    rewriter_base_url: str = ""
    rewriter_api_key: str = ""
    rewriter_extra_body: str = "{}"

    judge_model: str = "qwen/qwen3.8-27b"
    judge_base_url: str = ""
    judge_api_key: str = ""
    judge_extra_body: str = '{"reasoning_effort": "none"}'

    # --- Corpus ---
    github_token: str = ""
    fastapi_repo: str = "fastapi/fastapi"
    fastapi_ref: str = "0.162.0"  # pinned release: reproducible corpus
    max_discussions: int = 2000
    max_issues: int = 400
    only_answered_discussions: bool = True

    # --- Chunking (decisions to test, not defaults: see eval/ablation.py) ---
    chunk_strategy: Literal["markdown", "fixed"] = "markdown"
    chunk_size: int = 400  # tokens (cl100k)
    chunk_overlap: int = 60  # tokens

    # --- Embeddings / reranker (local ONNX via fastembed, no torch) ---
    dense_model: str = "BAAI/bge-small-en-v1.5"
    query_prefix: str = "Represent this sentence for searching relevant passages: "
    sparse_model: str = "Qdrant/bm25"
    rerank_model: str = "Xenova/ms-marco-MiniLM-L-6-v2"
    model_cache_dir: str = str(ROOT / ".cache" / "fastembed")

    # --- Vector store ---
    qdrant_url: str = ""
    qdrant_api_key: str = ""
    qdrant_path: str = str(DATA_DIR / "qdrant")
    collection: str = "librarian"

    # --- Retrieval ---
    retrieval_mode: RetrievalMode = "hybrid"
    candidate_k: int = 30  # per retriever, before fusion
    rrf_k: int = 60
    use_reranker: bool = True
    rerank_candidates: int = 20
    top_k: int = 6  # chunks sent to the generator
    # Below this cross-encoder logit for the best chunk we answer "I don't know"
    # without calling the LLM. Calibrate on the unanswerable eval questions.
    abstain_threshold: float = -6.0

    # --- Query rewriting ---
    rewrite_mode: Literal["auto", "always", "never"] = "auto"

    # --- Service ---
    rate_limit_per_minute: int = 10
    max_question_chars: int = 1000
    telemetry_db: str = str(DATA_DIR / "telemetry.db")
    cors_origins: str = "*"

    def role(self, name: LLMRole) -> RoleConfig:
        return RoleConfig(
            model=getattr(self, f"{name}_model"),
            base_url=getattr(self, f"{name}_base_url") or self.llm_base_url,
            api_key=getattr(self, f"{name}_api_key") or self.llm_api_key,
            extra_body=json.loads(getattr(self, f"{name}_extra_body") or "{}"),
        )

    @property
    def processed_dir(self) -> Path:
        return DATA_DIR / "processed"

    @property
    def raw_dir(self) -> Path:
        return DATA_DIR / "raw"


@lru_cache
def get_settings() -> Settings:
    return Settings()
