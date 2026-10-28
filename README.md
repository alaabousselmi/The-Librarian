# The Librarian

A retrieval-augmented question-answering service for **FastAPI** developers. It answers from the
official FastAPI documentation, GitHub Discussions and GitHub issues — and cites the source of
every claim, or says "I don't know".

> CS496 AI Engineering — Project 2 (MedTech, Fall 2026). Plan: [`docs/PLAN.md`](docs/PLAN.md) ·
> Design: [`docs/design.md`](docs/design.md)

**Live service:** _not deployed yet (Hugging Face Spaces + Qdrant Cloud planned)_

## Quick start

Requirements: Docker, a free [Groq API key](https://console.groq.com/keys), and (optional, for
Discussions/issues) a GitHub token with public read access.

```bash
cp .env.example .env            # then fill LLM_API_KEY (and GITHUB_TOKEN)

# setup — download the corpus and build the index (one command)
docker compose run --rm app librarian build

# run — http://localhost:8000
docker compose up
```

<details>
<summary>Without Docker (Python 3.11+)</summary>

```bash
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev]" && librarian build         # setup (embedded Qdrant in data/qdrant, no server)
librarian serve                                    # run
librarian ask "How do I run code after returning a response?"
```
</details>

## How it works

```
                    offline                                           online
 FastAPI docs ─┐                                    question ─► rewrite (only if short / multi-part, ALLaM-7B)
 Discussions ──┼─► clean ─► chunk ─► embed (bge-small) ─┐            │
 Issues ───────┘   (inline   (markdown-   + BM25 sparse  │            ▼
                   code)     aware)                      ▼     BM25 ──┐
                                                  Qdrant ◄─────dense ─┴─► RRF fusion ─► cross-encoder rerank
                                                                                          │
                                         "I don't know" ◄── best score below threshold ──┤
                                                                                          ▼
                                                              gpt-oss-120b answers from the top chunks,
                                                              citing [n] per claim ─► citations validated
```

| Component | Choice |
|---|---|
| Corpus | FastAPI docs (146 pages) + answered GitHub Discussions + closed issues |
| Chunking | structure-aware markdown chunker (code blocks kept whole, heading breadcrumbs, deep-link anchors) |
| Index | Qdrant: dense `bge-small-en-v1.5` + BM25 sparse vectors, metadata filters |
| Retrieval | hybrid BM25 + dense, Reciprocal Rank Fusion, `ms-marco-MiniLM-L-6-v2` reranker |
| Generation | `openai/gpt-oss-120b` (OpenAI 120B MoE) on Groq free tier |
| Query rewrite | `allam-2-7b` (SDAIA 7B) |
| Eval judge | `qwen/qwen3.8-27b` (Alibaba 27B) — a different family from the generator |

All LLM roles use an OpenAI-compatible client: switch any of them to another provider (paid or a
local Ollama) by editing `.env`.

### API

| Method | Path | |
|---|---|---|
| `POST` | `/api/ask` | `{"question": "...", "filters": {"source_types": ["docs"]}, "debug": false}` |
| `POST` | `/api/feedback` | `{"request_id": "...", "rating": 1 \| -1, "comment": "..."}` |
| `GET` | `/api/search?q=...&mode=hybrid&rerank=true` | retrieval only, no LLM |
| `GET` | `/api/stats` | requests, p50/p95 latency, cost/request, feedback |
| `GET` | `/healthz`, `/readyz` | liveness / index loaded |

Interactive docs at `/docs`.

## Evaluation

```bash
python eval/ablation.py                    # retrieval: recall@k, MRR, search latency for 4 configs
python eval/generation_eval.py             # correctness, faithfulness, citation accuracy, "I don't know"
python eval/build_dataset.py --n 60        # draft new Q&A candidates for human review
python eval/load_test.py --url http://localhost:8000
```

Eval set: [`data/eval/questions.jsonl`](data/eval/questions.jsonl) — question, reference answer,
gold source passage(s), answerable flag.

## Results

120-question eval set (104 answerable, 16 unanswerable; docs, Discussions, issues, multi-part, code,
version questions), full corpus of 1 539 documents. Generator `gpt-oss-120b`, judge `qwen3.8-27b`.
v1 and v2 were run back to back (provider latency drifts by hours, see the optimisation report).

| Metric | v1.0 baseline | v2.0 optimised |
|---|---|---|
| Recall@5 / MRR@10 (hybrid + rerank) | 0.755 / 0.591 | 0.755 / 0.591 (retrieval unchanged) |
| Correctness | 0.896 (second run: 0.908) | 0.896 |
| Faithfulness | 0.973 | 0.936 |
| Citation accuracy | 0.976 | 0.959 |
| "I don't know" recall / false IDK | 1.00 / 4.8% | 1.00 / 3.8% |
| p50 / p95 latency | 1.96 s / 3.66 s | 1.84 s / **2.78 s (−24%)** |
| Generation p95 | 2.59 s | **1.28 s (−51%)** |
| Cost / request (list price) | $0.000375 | $0.000364 |

* Retrieval ablation (BM25 0.66 → dense 0.59 → hybrid 0.70 → + reranker **0.76** recall@5):
  [`eval/results/ablation.md`](eval/results/ablation.md); chunking experiment:
  [`eval/results/chunking.md`](eval/results/chunking.md).
* Abstention: 13 of 16 unanswerable questions are stopped before any LLM call
  ([`eval/results/abstain_calibration.md`](eval/results/abstain_calibration.md)); the generator refuses the rest.
* Judge: same verdict on 40/40 re-judged answers; human check sheet in `data/eval/judge_check.csv`.
* Load test (local, 3 concurrent clients): 30/30 OK, p50 3.8 s / p95 4.5 s, ~1 request/s, bounded by the
  CPU reranker ([`eval/results/load_test.md`](eval/results/load_test.md)).
* Cost: ~$1/month at 100 questions/day, ~$110/month at 100× ([`docs/cost_model.md`](docs/cost_model.md)).

Optimisation report: [`docs/optimisation.md`](docs/optimisation.md) ·
Corpus: [`docs/corpus.md`](docs/corpus.md) ·
Postmortem: [`docs/postmortem.md`](docs/postmortem.md)

## Repository layout

```
librarian/          service code (ingest, chunking, index, retrieval, generation, API)
  ingest/           FastAPI docs + GitHub loaders
  api/              FastAPI app + web UI
eval/               retrieval eval, ablation, generation eval, dataset builder, load test
data/eval/          eval questions (committed); data/raw|processed|qdrant are rebuilt, not committed
docs/               plan, design, optimisation report, postmortem
tests/              unit tests (run in CI)
```

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md). Never commit `.env`, API keys, or raw GitHub data.

## Contributions

| Member | Main contributions |
|---|---|
| Mohamed Amine Zouaoui | Packaging, config and data models; chunking; embeddings and the Qdrant index; LLM client with cost tracking; query rewriting; hybrid search with RRF; cross-encoder reranking; grounded answers with validated citations; abstention and its calibration; CLI; generation eval and judge validation; Week 8 optimisation; design doc |
| Alaeddine Bousselmi | FastAPI docs loader; GitHub Discussions/issues loader; corpus size, licence and permission; hand-written gold questions; postmortem |
| Seifeddine Knani | Chunk-size experiments; second batch of gold questions from real Discussions/issues; LLM-drafted questions and their review; retrieval eval; ablation; optimisation report; cost model |
| Walid Fakhfakh | Telemetry; HTTP API; web chat page with feedback; load test; unit tests; Docker and Compose; CI; README |

Per-task authorship is in the git history (one commit per task).

## License

Code: MIT. Corpus: FastAPI documentation (MIT, © Sebastián Ramírez) and public GitHub
Discussions/issues of `fastapi/fastapi`; usernames are not stored.
