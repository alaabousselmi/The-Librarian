# Design

Living document — first version Week 1, completed Week 2 with measured numbers.

## 1. Corpus and users

| Source | What | Size (Week 1) | Shape |
|---|---|---|---|
| Docs | `fastapi/fastapi` `docs/en/docs/**/*.md` at a pinned ref | 146 pages, ~1.7 M chars (~425 k tokens) | long tutorial pages, many code examples, explicit `{ #anchors }` |
| Discussions | answered GitHub Discussions (GraphQL) | up to 2 000 | question + accepted answer + top replies; informal, sometimes outdated |
| Issues | closed issues with replies (REST) | up to 400 | bug reports, stack traces |

FastAPI moved user Q&A from issues to Discussions, so Discussions carry most of the community
knowledge; issues add bug/behaviour reports.

**Users:** our classmates (all build APIs with FastAPI in other courses), and Python developers.
They ask "how do I…", "why does … fail", "since which version…".

**Permission / privacy:** docs are MIT-licensed; Discussions and issues are public. We **never store
GitHub usernames** — authors are reduced to their role (maintainer / contributor / community), which
is what matters for trust. Excluded: `fastapi-people.md` (lists of people). Raw data is not committed.

## 2. Ingestion

* Docs are downloaded as a tarball of a pinned ref (reproducible, one HTTP request).
* `{* ../../docs_src/x.py hl[..] ln[a:b] *}` and `{!..!}` include directives are **resolved and the real
  code inlined** — otherwise the code examples users ask about would not exist in the index.
* MkDocs syntax is normalised: admonitions → `**Tip: …**`, `<dfn>/<abbr>` tooltips → `term (definition)`,
  `:::` mkdocstrings directives dropped.

## 3. Chunking

Two strategies, both in `librarian/chunking.py`, compared in the ablation (chunking is a decision to
test, not a default):

* **markdown** (default): parse into heading / code / text blocks; new chunk at every H1–H3;
  pack blocks greedily up to `CHUNK_SIZE` tokens; overlap by whole trailing blocks up to
  `CHUNK_OVERLAP` tokens; **never split a code fence** unless the fence alone exceeds the budget
  (then split by lines and re-fence each part). Each chunk keeps its heading path and the anchor of
  its section, so citations deep-link (`…/tutorial/query-params/#defaults`).
  The embedded text is prefixed with the breadcrumb (`Query Parameters > Defaults`) so short chunks
  keep their context.
* **fixed**: sliding window of N tokens — the naive baseline.

Week 2 grid: strategy × size {200, 400, 800} × overlap {0, 60}, chosen on recall@5.

## 4. Index choice: Qdrant

* Dense vectors **and** BM25 sparse vectors (IDF computed server-side) in one collection — hybrid
  search without keeping two systems in sync.
* Payload filters on `source_type`, `section`, `created_at` for metadata filtering.
* Same client code runs **embedded** (a local folder: zero setup for dev, tests, CI), in **Docker**,
  or on **Qdrant Cloud free tier** (1 GB) for the deployed service.
* Alternatives considered: pgvector (needs a separate BM25 / `tsvector` is not BM25), FAISS / flat
  file (no filters, no sparse, rebuild on every change), Elasticsearch (too heavy for free hosting).

Embeddings: `BAAI/bge-small-en-v1.5` (384-d) via fastembed/ONNX: free, CPU-fast, no torch in the image.

## 5. Retrieval

1. Optional **query rewrite** (ALLaM-2-7B) only for short (< 4 words) or multi-part questions;
   returns up to 3 sub-queries; the original question is always searched too.
2. **BM25** top-30 and **dense** top-30 per query, fused with **Reciprocal Rank Fusion** (k = 60);
   multiple sub-queries are fused the same way.
3. **Cross-encoder rerank** (`ms-marco-MiniLM-L-6-v2`) of the top 20 against the *original* question;
   keep top 6.
4. If the best rerank logit < `ABSTAIN_THRESHOLD` → "I don't know" **without calling the LLM**
   (saves cost, avoids hallucinating on out-of-scope questions). Threshold calibrated in Week 2.

## 6. Generation

* gpt-oss-120b (reasoning effort low), temperature 0.1, sources numbered `[1]…[n]` with type, date, heading path and URL.
* Rules: answer only from sources, cite every factual sentence, exact "I don't know …" sentence when
  the sources do not answer, prefer docs over discussions when they disagree.
* The system prompt is static and first → eligible for provider prompt caching (Week 3).
* Citations are parsed and **validated**: numbers that do not correspond to a retrieved chunk are
  dropped and counted (`invalid_citations`).

## 6b. First measurements (Week 1, 20 seed questions — too few to conclude)

| Config | recall@5 | MRR@10 | search p50 |
|---|---|---|---|
| BM25 only | 0.80 | 0.71 | 25 ms |
| Dense only | 0.90 | 0.75 | 11 ms |
| Hybrid (RRF) | 0.90 | 0.75 | 48 ms |
| Hybrid + reranker | 0.875 | 0.74 | 880 ms |

The reranker adds ~0.85 s on a laptop CPU and does not help yet on easy seed questions — to
re-measure on the full 120-question set before deciding; prime Week 3 lever (fewer candidates,
skip when first stage is confident).

## 7. Evaluation design

* Gold passages are stored as **text + doc_id**, not chunk ids, so the test set survives re-chunking.
  A retrieved chunk is a hit if it is from the gold document and contains ≥ 60% of the gold passage.
* Retrieval and generation are measured **separately** (recall@k vs. faithfulness/correctness).
* The judge (Qwen3.8-27B) is a different family from the generator (gpt-oss) to limit self-preference;
  we validate it by hand on a sample.

## 8. Known failure cases (to verify and extend with real logs in Week 2)

| # | Case | Why it breaks | Mitigation / status |
|---|---|---|---|
| 1 | API reference pages (`::: fastapi.FastAPI`) | content is generated from docstrings at build time; we drop the directive, so parameter-level reference is missing | Week 2: extract docstrings from the installed `fastapi` package |
| 2 | Release notes / version questions | "since which version" questions need the right `## 0.x.y` section; observed: *"Since which version is Annotated supported?"* answered **0.105.0** (correct: 0.95.0) from a release-notes chunk that mentions Annotated | Week 2: add more `version` questions, boost the tutorial statement, tell the model release notes list *changes*, not first support |
| 3 | Code-only answers | BM25 matches identifiers well, dense embeddings do not | hybrid search; keep code fences whole |
| 4 | Long code blocks (> chunk size) | split across chunks, the explanation may be in another chunk | breadcrumb prefix; consider larger size for code |
| 5 | Outdated Discussions | answers written for old FastAPI/Pydantic v1 | show date + source type to the model; prefer docs |
| 6 | Cross-references ("see the previous section") | the referenced text is in another chunk/page | rewriting + multi-query; known limitation |
| 7 | Tables (e.g. status codes, settings) | a row out of context loses its header | small tables stay in one block; to measure |
| 8 | Multi-part questions | one retrieval rarely covers both parts; reranking against the full question let the dominant part take every slot | rewrite into sub-queries **and rerank each sub-query separately**, interleaving results (fixed Week 1) |
| 9 | Questions about other frameworks | dense retrieval always returns *something* | rerank threshold + model "I don't know" |
| 10 | Ambiguous intent: "run code after the response" | middleware ("before and after the response") outranks background tasks for the reranker | rewrite / let the generator mention both; add to eval set |
| 11 | Prompt injection inside Discussions text | user-written content is passed to the LLM | system prompt rules; sources are quoted as data |

## 9. Provider limits (measured 2026-10-21 from Groq response headers)

| Model | Role | Tokens / min | Requests / day |
|---|---|---|---|
| `openai/gpt-oss-120b` | generator | 8 000 | 1 000 |
| `qwen/qwen3.8-27b` | judge | 8 000 | 1 000 |
| `allam-2-7b` | rewriter | 6 000 | 7 000 |

A request sends ~1 800 input + ~250 output tokens to the generator, so the free tier serves only
**~3–4 questions per minute** and ~1 000 per day. Beyond that, requests queue behind the quota
(observed: generation 0.5 s → 10–17 s). Fewer tokens per request therefore raises *capacity* as well
as cutting cost — the main Week 3 lever. The eval paces itself to the TPM limit so that measured
latency is the system's, not the queue's.
