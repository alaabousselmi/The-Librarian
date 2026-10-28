"""Thin LLM client over any OpenAI-compatible endpoint (Groq, OpenRouter, Ollama, OpenAI...).

Each role (generator / rewriter / judge) has its own model and can point at its
own provider, so moving one role to a paid model later is a .env change.
Every call returns token usage, latency and a list-price cost estimate, which
feed the cost model even while we run on a free tier.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from functools import lru_cache

from openai import OpenAI

from librarian.config import LLMRole, Settings, get_settings

# USD per 1M tokens (input, output) at the provider's *paid* list price, used to
# price requests for the cost model even though the free tier bills $0.
# Source: third-party price trackers, Oct 2026 — verify on https://groq.com/pricing before
# quoting numbers in the report. Models missing here are priced at $0 (allam-2-7b: no public price).
PRICES: dict[str, tuple[float, float]] = {
    "openai/gpt-oss-120b": (0.15, 0.60),
    "openai/gpt-oss-20b": (0.075, 0.30),
    "qwen/qwen3.8-27b": (0.80, 4.00),  # preview model
    "meta-llama/llama-3.1-8b-instruct": (0.05, 0.08),  # rewriter stand-in where allam-2-7b is not offered
}

THINK = re.compile(r"<think>.*?</think>", re.S)


@dataclass
class LLMResult:
    text: str
    model: str
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    latency_ms: float

    @property
    def cost_usd(self) -> float:
        p_in, p_out = PRICES.get(self.model, (0.0, 0.0))
        return (self.input_tokens * p_in + self.output_tokens * p_out) / 1e6


@lru_cache
def _client(base_url: str, api_key: str, timeout: float, retries: int) -> OpenAI:
    return OpenAI(base_url=base_url, api_key=api_key or "missing-key", timeout=timeout, max_retries=retries)


class LLM:
    def __init__(self, role: LLMRole, settings: Settings | None = None):
        self.s = settings or get_settings()
        self.cfg = self.s.role(role)
        self.role = role
        self.client = _client(self.cfg.base_url, self.cfg.api_key, self.s.llm_timeout_s, self.s.llm_max_retries)

    @property
    def model(self) -> str:
        return self.cfg.model

    def complete(self, messages: list[dict], *, max_tokens: int = 800, temperature: float = 0.0,
                 json_mode: bool = False) -> LLMResult:
        kwargs = {}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        if self.cfg.extra_body:
            kwargs["extra_body"] = self.cfg.extra_body
        t0 = time.perf_counter()
        resp = self.client.chat.completions.create(
            model=self.cfg.model, messages=messages, max_tokens=max_tokens,
            temperature=temperature, **kwargs,
        )
        latency = (time.perf_counter() - t0) * 1000
        usage = resp.usage
        cached = 0
        if usage and getattr(usage, "prompt_tokens_details", None):
            cached = getattr(usage.prompt_tokens_details, "cached_tokens", 0) or 0
        text = THINK.sub("", resp.choices[0].message.content or "").strip()
        return LLMResult(
            text=text,
            model=self.cfg.model,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            cached_tokens=cached,
            latency_ms=latency,
        )
