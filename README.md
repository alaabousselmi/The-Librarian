# The Librarian

A retrieval-augmented question-answering service for **FastAPI** developers. It answers from the
official FastAPI documentation, GitHub Discussions and GitHub issues — and cites the source of
every claim, or says "I don't know".

> CS496 AI Engineering — Project 2 (MedTech, Fall 2026). Plan: [`docs/PLAN.md`](docs/PLAN.md) ·
> Design: [`docs/design.md`](docs/design.md)

**Live service:** _URL added in Week 2 (Hugging Face Spaces)_

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

_Filled in Week 2 (baseline) and Week 3 (after optimisation)._

First numbers (Week 1, 25 seed questions — indicative only): correctness 0.96, faithfulness 0.98,
citation accuracy 0.98, "I don't know" recall 1.0, p50 1.6 s / p95 2.5 s, $0.00037 per request at list price.

| Metric | v1.0 baseline | v2.0 optimised |
|---|---|---|
| Recall@5 (hybrid + rerank) | | |
| Correctness | | |
| Faithfulness | | |
| Citation accuracy | | |
| "I don't know" recall | | |
| p50 / p95 latency | | |
| Cost / request (list price) | | |

Ablation table: [`eval/results/ablation.md`](eval/results/ablation.md) ·
Optimisation report: [`docs/optimisation.md`](docs/optimisation.md) ·
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

| Member | Role | Main contributions |
|---|---|---|
| _name_ | A — Data & Index | |
| _name_ | B — Retrieval & Eval | |
| _name_ | C — Generation & LLM | |
| _name_ | D — Service & Ops | |

## License

Code: MIT. Corpus: FastAPI documentation (MIT, © Sebastián Ramírez) and public GitHub
Discussions/issues of `fastapi/fastapi`; usernames are not stored.
