# Week 8 optimisation report

Target: **−50% cost per request or p95 latency**, losing **≤ 2 points** of accuracy, measured
before and after on the **same** test set (`data/eval/questions.jsonl`, 120 questions).

Every row is one full run of `python eval/generation_eval.py` (retrieval + generation + LLM judge)
through OpenRouter, generator `openai/gpt-oss-120b`, judge `qwen/qwen3.8-27b`. Cost is at list price
(`librarian/llm.py`). Summaries are in `eval/results/<run>.json`.

## Two things we learned before trusting any number

1. **Run-to-run noise.** The unchanged v1 configuration, run twice, scored correctness 0.908 and 0.896:
   about ±1.2 points of noise, mostly from the generator (temperature 0.1). A change that loses
   less than ~1.5 points is indistinguishable from no change.
2. **Provider latency drifts.** The same v1 configuration had p95 **10.6 s** in a run finishing at 00:06 and **3.7 s** in one finishing at 01:45.
   Almost all of it is generation time on whichever OpenRouter provider served the call. Latency is
   therefore only compared between runs made **back to back**. The final before/after pair below was run
   consecutively.

## Baseline (v1.0)

| Metric | Run 1 (`baseline_v1`) | Run 2 (`baseline_v1_rerun`, back to back with v2) |
|---|---|---|
| Correctness | 0.908 | 0.896 |
| Faithfulness | 0.961 | 0.973 |
| Citation accuracy | 0.972 | 0.976 |
| "I don't know" recall / false IDK | 1.00 / 0.029 | 1.00 / 0.048 |
| p50 / p95 latency | 4 070 / 10 567 ms | 1 955 / 3 659 ms |
| Generation p50 / p95 | 3 463 / 9 459 ms | 867 / 2 593 ms |
| Reranker p50 | 945 ms | 950 ms |
| Avg input / output tokens | 1 643 / 226 | 1 645 / 214 |
| Cost / request (list price) | $0.000381 | $0.000375 |

## Changes

Each change measured in isolation against the v1 configuration, then the kept ones together.

| # | Change | How | Cost/request | p50 / p95 ms | Correctness | Faithfulness | Kept? |
|---|---|---|---|---|---|---|---|
| 1 | Fewer chunks in the prompt: top_k 6 → 4 | `--top-k 4` | $0.000298 (−22%) | 3 675 / 11 487 | 0.879 (−2.9) | 0.956 | ✗ accuracy |
| 2 | Smaller generator: gpt-oss-120b → 20b | `GENERATOR_MODEL` | $0.000190 (−50%) | 4 383 / 15 120 | 0.854 (−5.4) | 0.816 | ✗ accuracy, slower |
| 3 | Fewer rerank candidates: 20 → 10 | `RERANK_CANDIDATES=10` | $0.000379 | 3 462 / 8 124 | 0.875 (−3.3) | 0.934 | ✗ accuracy (false IDK 2.9% → 7.7%) |
| 4 | Route the generator to the lowest-latency provider | OpenRouter `provider.sort=latency` | $0.000374 | 2 025 / 9 588 | 0.892 (−1.7) | 0.949 | ✗ p95 barely moves |
| 5 | Route to the highest-throughput provider | `provider.sort=throughput` | $0.000374 | 2 148 / 8 873 | 0.888 (−2.1) | 0.951 | ✗ superseded by 7 |
| 6 | Shorter answers: "≤ ~150 words + one code example" | prompt rule 6 | $0.000355 (−7%) | 2 267 / 7 327 | 0.892 (−1.7) | 0.947 | ✓ |
| 7 | Pin the generator to Groq (fast inference, same list price) | `provider.order=["groq"]` | — | — | — | — | ✓ (with 6) |
| 8 | Truncate passages scored by the cross-encoder (1 000 / 600 chars) | retrieval-only test | — | rerank 1 245 → 1 102 / 610 ms | recall@5 0.755 → 0.668 / 0.639 | — | ✗ recall |

Not tried: prompt caching (the static system prompt is ~300 of ~1 650 input tokens, so at most ~9% of
input cost) and a semantic answer cache (no effect on a test set of distinct questions; worth it for real
traffic).

## Result (v2.0 = 6 + 7), back to back with the baseline

| Metric | v1 (`baseline_v1_rerun`) | v2 (`optimised_v2_groq`) | Δ |
|---|---|---|---|
| Correctness | 0.896 | 0.896 | ±0 (run 1 of v1: 0.908, −1.2) |
| Faithfulness | 0.973 | 0.936 | −3.7 |
| Citation accuracy | 0.976 | 0.959 | −1.7 |
| "I don't know" recall / false IDK | 1.00 / 0.048 | 1.00 / 0.038 | |
| p50 latency | 1 955 ms | 1 839 ms | −6% |
| **p95 latency** | **3 659 ms** | **2 778 ms** | **−24%** |
| Generation p95 | 2 593 ms | 1 276 ms | **−51%** |
| Avg output tokens | 214 | 180 | −16% |
| Cost / request | $0.000375 | $0.000364 | −3% |

Against the first baseline run (taken while OpenRouter was slow) v2 is −73% p95, but that comparison is
not fair: the provider's speed, not our change, explains most of it.

**Verdict: target not met end to end.** The LLM part of the latency is halved (generation p95 −51%) within
the accuracy budget (correctness unchanged). Once generation is fast, the remaining tail is our own
**CPU cross-encoder (~1 s per request)**, and every way of making it cheaper (fewer candidates, shorter
passages) cost 3–12 points. Cost cannot be halved within the budget either: the only −50% lever, the 20b
generator, loses 5.4 points of correctness and 14.5 of faithfulness.

The faithfulness drop (−3.7) is larger than the noise we measured on correctness. We keep v2 because
correctness and citation accuracy hold, but the shorter answer rule is the first thing to revisit if
users report unsupported claims.

## What did not work

* **Cheaper models and fewer chunks**: every cost lever lost more than 2 points (rows 1–2).
* **Fewer or shorter rerank inputs**: the cross-encoder is what moves recall@5 from 0.70 to 0.76, and it
  needs the full candidate list and full passages to do it (rows 3, 8).
* **Sorting providers by latency**: it optimises time-to-first-token; long answers from a slow provider
  still made the tail (row 4).

## Next levers (not done)

* Reranker on a GPU or a distilled/quantised cross-encoder: the only remaining big latency term.
* Answer cache for repeated questions (real traffic repeats; the eval set does not).
* Prompt caching on Groq for the static system prompt (small, ~9% of input tokens).
