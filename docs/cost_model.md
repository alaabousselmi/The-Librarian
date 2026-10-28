# Cost model

Measured on the 120-question eval set. Prices: list price per 1M tokens (input, output) from `librarian/llm.py`: `openai/gpt-oss-120b` $0.150 / $0.60, `openai/gpt-oss-20b` $0.075 / $0.30, `qwen/qwen3.8-27b` $0.800 / $4.00, `meta-llama/llama-3.1-8b-instruct` $0.050 / $0.08.
Embeddings, BM25 and the reranker run locally on CPU, so they cost CPU time, not money.

"Today" = 100 questions/day (the Week 2 target of ~100 questions from real users); peak = 10% of a day's traffic in one hour.

| | baseline_v1_rerun | optimised_v2_groq |
|---|---|---|
| generator | `openai/gpt-oss-120b` | `openai/gpt-oss-120b` |
| questions in run | 120 | 120 |
| requests that call an LLM | 89% | 89% |
| requests that also rewrite | 2% | 2% |
| avg input / output tokens | 1,648 / 214 | 1,713 / 180 |
| **cost / request** (list price) | **$0.000375** | **$0.000364** |
| cost / 1,000 requests | $0.375 | $0.364 |
| **today: 100 questions/day** |  |  |
| cost / day · month | $0.04 · $1.12 | $0.04 · $1.09 |
| fits Groq free tier? | yes | yes |
| reranker CPU at peak | 0.00 cores | 0.00 cores |
| **100×: 10,000 questions/day** |  |  |
| cost / day · month | $3.75 · $112.45 | $3.64 · $109.18 |
| fits Groq free tier? | no (peak 17/min vs 4.3/min) | no (peak 17/min vs 4.2/min) |
| reranker CPU at peak | 0.28 cores | 0.28 cores |

## Reading it

* **Today** the LLM bill is $1.09/month at list price, and $0 on the free tier, which is the binding constraint: 8,000 tokens/min and 1,000 requests/day for the generator, i.e. ~4.2 questions/min.
* **At 100×** the free tier no longer fits (requests/day and tokens/min), so the generator moves to the paid tier of the same provider: the cost is the 100× row, and nothing else in the system changes (models are config).
* Hosting: one CPU container (Hugging Face Spaces free tier, 2 vCPU) and Qdrant Cloud free tier (1 GB). The index is 19 650 points, 110 MB on disk in Qdrant (measured), and does not grow with traffic. The reranker is the only CPU-heavy step; the table shows the cores it needs at peak.
* Not included: eval runs (judge tokens), which are a one-off per experiment, not per user request.
