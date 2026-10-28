# The Librarian — 3-week work plan

**Goal (from the brief):** a *deployed* RAG service over a *real* corpus with *real users*, answering
with citations, with retrieval and generation measured separately, an ablation, and a Week 8
optimisation (−50% cost **or** p95 latency, ≤ 2 points accuracy lost).
Grading focus: **Works 25% · Measured 25% · Efficient 25%** (+ report/postmortem).

**Corpus:** FastAPI — official docs (146 pages) + GitHub Discussions (Q&A) + closed GitHub issues.
**Users:** classmates and Python developers who build APIs with FastAPI.

**Stack (all free):**

| Role | Choice | Why |
|---|---|---|
| Generator | `openai/gpt-oss-120b` (OpenAI, 120B MoE) on Groq free tier | strongest free model for grounded answers |
| Query rewriter | `allam-2-7b` (SDAIA, 7B) on Groq | different family + size, fast (~0.6 s) |
| Eval judge | `qwen/qwen3.8-27b` (Alibaba, 27B) on Groq | third family: the judge never grades its own family |
| Embeddings | `BAAI/bge-small-en-v1.5` (local, ONNX) | free, CPU-fast, 384-d |
| Keyword search | BM25 (Qdrant sparse vectors + IDF) | real BM25, same store as dense |
| Reranker | `ms-marco-MiniLM-L-6-v2` cross-encoder (local, ONNX) | free, ~20 ms for 20 pairs |
| Vector store | Qdrant (embedded locally / Docker / Qdrant Cloud free tier) | dense + sparse + metadata filters in one system |
| Service | FastAPI + static web UI, SQLite request/feedback log | |
| Hosting | Hugging Face Spaces (Docker, free) + Qdrant Cloud free 1 GB | |

All LLMs go through one OpenAI-compatible client, so moving any role to a paid model later is a `.env` change.

**Roles** (4 contributors — replace with names in README *Contributions*):
- **A — Data & Index:** ingestion, chunking, index.
- **B — Retrieval & Eval:** retrieval quality, eval dataset, retrieval eval, ablation.
- **C — Generation & LLM:** prompts, citations, abstention, generation eval, cost model.
- **D — Service & Ops:** API, UI, Docker, deployment, CI, users, feedback.

Status legend: ✅ done · 🔄 in progress · ⬜ to do

---

## Week 1 — Build the whole working system (due **Tue 21 Oct 2026**, today)

Most of the project lands this week: by the end of the day the full pipeline runs end to end
from a clean clone, is containerised, and has an eval harness ready to fill.

### A — Data & Index
- ✅ Repo, packaging (`pyproject.toml`), config via `.env`, `.gitignore` (no keys, no data)
- ✅ Docs loader: pinned tarball, inline `docs_src` code includes, strip MkDocs syntax, keep `{ #anchor }` for deep-link citations
- ✅ GitHub loader: Discussions (GraphQL) + closed issues (REST), cached, rate-limit aware, **no usernames stored**
- ✅ Chunkers: structure-aware markdown (never splits code fences, heading breadcrumbs) + naive fixed window baseline
- ✅ Build the index: dense + BM25 in Qdrant, metadata payload — 146 pages → 2 295 chunks (mean 194 tokens), ~4 min on CPU
- ⬜ **needs `GITHUB_TOKEN`** — run ingestion with discussions + issues and rebuild the index

### B — Retrieval & Eval
- ✅ Retrieval modes `bm25 | dense | hybrid` (RRF), reranker on/off, metadata filters, multi-query merge
- ✅ Eval data format `data/eval/questions.jsonl` (question, reference answer, gold source passages, answerable flag)
- ✅ `eval/build_dataset.py`: draft Q&A candidates from sampled chunks (LLM) with verbatim-quote check, for human review
- ✅ 25 hand-written seed questions incl. 5 unanswerable (gold passages verified verbatim)
- ✅ `eval/retrieval_eval.py` + `eval/ablation.py` — first run: hybrid recall@5 0.90 vs BM25 0.80 (20 q, see `eval/results/ablation.md`)

### C — Generation & LLM
- ✅ OpenAI-compatible LLM client per role, token usage + list-price cost per call
- ✅ Query rewriting (auto-gated: only short / multi-part questions pay for an LLM call)
- ✅ Grounded prompt, `[n]` citations validated against retrieved chunks, "I don't know" (model + reranker threshold)
- ✅ `eval/generation_eval.py`: correctness, faithfulness, citation accuracy, abstention — judged by Qwen3.8
- ✅ Smoke test end to end with the Groq key + first generation eval on the seed set (`eval/results/generation_seed.json`)
- ✅ Models re-chosen from Groq's live list (Llama 3.3 70B was retired): gpt-oss-120b / allam-2-7b / qwen3.8-27b
- ✅ Fixes from the first real runs: multi-part reranking, native `【n】` citations, eval pacing under the 8k TPM free-tier limit

### D — Service & Ops
- ✅ API: `/api/ask`, `/api/feedback`, `/api/search`, `/api/stats`, `/healthz`, `/readyz`; per-IP rate limit
- ✅ Web UI: ask, source filters, clickable citations, 👍/👎 + comment
- ✅ Telemetry: every request logged (latency per stage, tokens, cost) + feedback table
- ✅ Unit tests (19: chunking, loaders, RRF, citations, API with fake pipeline) + GitHub Actions CI (ruff + pytest + docker build)
- ✅ `Dockerfile` (models baked in, 933 MB) + `docker-compose.yml` (Qdrant + app) — README setup/run commands verified end to end
- ✅ README: one setup command, one run command, architecture, results placeholders, Contributions
- ✅ `docs/design.md` first version: chunking, index choice, known failure cases
- ⬜ **needs you** — create the GitHub repo, push, add teammates as collaborators

**Week 1 results (25 seed questions):** correctness 0.96 · faithfulness 0.98 · citation accuracy 0.98 · "I don't know" recall 1.0, false IDK 0 · p50 1.6 s / p95 2.5 s · $0.00037/request at list price · hybrid recall@5 0.90.

**Exit criteria Week 1:** `docker compose run --rm app librarian build` then `docker compose up` answers a FastAPI
question with citations in the browser; CI green; eval scripts run on the seed set.

---

## Week 2 — Measure it and put it in front of real users (Wed 22 → Tue 28 Oct)

Corresponds to the brief's "working version, end of Week 7". This week is about **evidence**.

### A — Data & Index
- ✅ Chunking experiments: `markdown` 200/400/800 × overlap 0/60 vs `fixed` 400 on the docs subset → keep markdown 400/60 (design.md §3)
- ⬜ Handle known gaps: API reference pages (`::: fastapi.X` docstrings), long release notes, tables
- ✅ Pin `FASTAPI_REF` to `0.162.0`; corpus stats in `docs/corpus.md` (1 539 documents, 2.23 M tokens, 19 650 chunks)

### B — Retrieval & Eval
- ✅ Grow eval set to **120 pairs** (new rows `verified: false` until a second teammate checks them) (≥ 15 unanswerable, mix of docs / discussions / multi-part / code / "since which version")
  — every pair reviewed by a second teammate, `verified: true`
- ✅ Retrieval eval: recall@{1,3,5,10}, MRR per mode
- ✅ **Ablation table**: BM25 only · dense only · hybrid · hybrid + reranker (and rewrite on/off)
- ✅ Search-step latency p50/p95

### C — Generation & LLM
- ✅ Generation eval on full set: correctness, faithfulness, citation accuracy, "I don't know" precision/recall
- ✅ Calibrate `ABSTAIN_THRESHOLD` on unanswerable questions (-6.0 → -0.5); tune prompt from failure analysis
- 🟡 Hand-check 20 judge verdicts: sheet exported (`data/eval/judge_check.csv`), human grades pending; judge self-agreement 40/40
- ✅ Cost model: cost/request today and at 100× traffic (`docs/cost_model.md`)

### D — Service & Ops
- ⬜ **Deploy**: Hugging Face Spaces (Docker) + Qdrant Cloud; public URL in README
- ⬜ Persist telemetry beyond container restarts (export job or hosted Postgres)
- ⬜ Real users: share with classmates + FastAPI study group, target ≥ 30 users / ≥ 100 questions; collect 👍/👎
- 🟡 End-to-end latency p50/p95: local load test done; from real logs once deployed
- ⬜ `docs/design.md` complete, with failure cases observed in real logs

**Exit criteria Week 2:** deployed URL, ablation table, generation metrics, real feedback numbers — the "working version" baseline frozen and tagged `v1.0`.

---

## Week 3 — Make it cheaper and faster, then ship the report (Wed 29 Oct → Tue 4 Nov, demo first session after)

Corresponds to the brief's Week 8. Same test set before and after, every change measured.

### Optimisation (all roles, one lever each)
- ✅ Baseline numbers from `v1.0`: cost/request, p50/p95, correctness, faithfulness
- ✅ **C:** smaller generator / fewer chunks: measured, both rejected (accuracy loss > 2 points)
- ⬜ **C:** prompt caching for the fixed system prompt (measure cached tokens)
- ✅ **B:** fewer rerank candidates: measured, rejected (−3.3 points)
- ⬜ **D:** semantic answer cache for repeated questions (embedding similarity ≥ threshold)
- ⬜ **A:** smaller index (int8 / binary quantisation in Qdrant), cheaper embeddings
- ✅ Keep a change only if accuracy drops ≤ 2 points; target **−50% p95 or cost**
- ✅ `docs/optimisation.md`: one row per change, before / after numbers

### Hand-in
- ⬜ Report (≤ 6 pages): corpus & users · pipeline design · retrieval + ablation · generation results · Week 8 · failure cases + cost model
- ✅ `docs/postmortem.md` — real problems and what we learned (a postmortem with no problems loses points)
- ✅ README results section filled; Contributions section per member
- ⬜ Clean-clone test on a fresh machine; secret scan (no keys, no personal data)
- ⬜ Demo script + rehearsal (live question, citations, ablation slide, before/after slide)
- ⬜ Tag `v2.0`

---

## Deliverables checklist (from the brief)

| Deliverable | Where | Week |
|---|---|---|
| README: one setup + one run command, results, Contributions | `README.md` | 1 → 3 |
| Deployed service with URL | HF Spaces | 2 |
| Eval questions + answers + source passages | `data/eval/` | 1 → 2 |
| Retrieval eval, generation eval, ablation script | `eval/` | 1 → 2 |
| Chunking, index choice, failure cases | `docs/design.md` | 1 → 2 |
| Before / after optimisation report | `docs/optimisation.md` | 3 |
| Postmortem | `docs/postmortem.md` | 3 |
| Report (≤ 6 pages) | `docs/report.pdf` | 3 |
