# Postmortem

Written in Week 3. Blameless: describe what happened, why, and what we changed. A postmortem with no
problems loses points — log problems here **as they happen** during the three weeks.

## Incident / problem log

| Date | What went wrong | Impact | Root cause | Fix / lesson |
| --- | --- | --- | --- | --- |
| 2026-10-21 | `<dfn title='…'>` tooltips with single quotes were left as raw HTML in the indexed text | noisy chunks on pages like dependencies-with-yield | regex only handled double quotes | fixed regex + unit test; lesson: inspect ingested text, not just counts |
| 2026-10-21 | One chunk was 2 530 tokens (budget 400) | a base64 image string in a code block dominated a chunk | code splitter only split between lines | truncate absurdly long lines; overlap can no longer push a chunk over budget; tests added |
| 2026-10-21 | Index had 2 296 points for 2 295 chunks | one stale chunk from the previous build was searchable | Qdrant embedded mode on Windows kept points across delete+create | `recreate()` now also deletes all points; lesson: assert count == chunks after indexing |
| 2026-10-21 | Generator `llama-3.3-70b-versatile` returned 404 model_not_found | no answers at all | Groq retired the model; the plan relied on a blog list | re-probed `/models`, moved to gpt-oss-120b / allam-2-7b / qwen3.8-27b; lesson: check the provider's live model list, models are config not code |
| 2026-10-21 | Multi-part question "enable CORS? and how to test?" answered only the CORS half | half of the answer was "I don't know" although the testing docs were retrieved | reranker scored all candidates against the full question, so the dominant part took all 6 slots | rerank each rewritten sub-query against its own candidates and interleave; regression test added |
| 2026-10-21 | Faithfulness 0.71 on the first generation eval | correct answers judged "uncited" | gpt-oss sometimes cites as `【2】` / `【2†L1-L3】`, our parser only knew `[2]` | normalise native citations before parsing; test added; lesson: read the judge's reasons before trusting a metric |
| 2026-10-21 | p50 latency 11 s in the first generation eval vs ~2 s by hand | latency numbers meaningless | free tier = 8 000 tokens/min for gpt-oss-120b; the SDK silently retried 429s | eval paces to the TPM limit; limits documented in design.md |
| 2026-10-21 | `librarian build` crashed inside Docker: PermissionError on `site-packages/data` | the README setup command did not work | data dir was derived from the package location, which is site-packages when installed non-editable | `DATA_DIR` env var, set in the Dockerfile; lesson: test the exact README commands, not just the dev setup |
| 2026-10-21 | include directives *inside* code fences were not resolved (7 cases, e.g. templates, JS clients) | code examples missing | loader skipped all lines in fences | resolve includes in fences too |
| 2026-10-27 | Seed question q023 ("built-in admin panel?") labelled unanswerable became answerable | an "I don't know" would have been scored correct although the corpus now answers it | labels were written against the docs-only corpus; Discussions added an answer (FastAdmin, SQLAdmin, …) | relabelled; every unanswerable question re-grepped against the full corpus (2 more drafts replaced); lesson: an eval label depends on the corpus, re-check when the corpus changes |
| 2026-10-27 | Week 1 recall@5 0.90 dropped to 0.76 on the full set | the Week 1 number overstated retrieval quality | 20 easy docs-only seed questions on a 146-page corpus; now 104 questions incl. community ones on 1 539 documents | report only full-set numbers; lesson: 20 questions is a smoke test, not a measurement |
| 2026-10-27 | `librarian index --overlap 0` silently built with overlap 60 | the overlap-0 chunking experiment would have measured the wrong thing | `overlap or settings.chunk_overlap` treats 0 as "not given" | `is None` checks; lesson: never use `or` for numeric defaults |
| 2026-10-27 | Indexing 19 650 chunks was estimated at ~45 min | slow experiment loop (each chunking variant = a full re-embed) | encoder batches are padded to their longest text; chunks were in document order (mean 113 tokens, max 414) | sort chunks by length before batching: 17 min; chunking grid run on the docs subset |
| 2026-10-27 | `librarian` command suddenly "No module named librarian"; embedded Qdrant crawled | lost time, misleading timings | repo lives in an iCloud-synced folder: macOS set the `hidden` flag on the venv's `.pth` files (Python skips hidden `.pth`), and iCloud re-uploaded the Qdrant files on every write | `chflags nohidden`, Qdrant in Docker (as in `docker compose`); lesson: keep venvs and data out of synced folders |
| 2026-10-27 | Half of the LLM-drafted eval questions were unusable (44 of 87 dropped) | review time | random chunk sampling over-samples the 7 500-line release notes (trivia: who translated what) and passages that are questions, not answers | review every draft; stratify by page next time; lesson: synthetic questions are cheap to make and expensive to check |
| 2026-10-27 | `allam-2-7b` (rewriter) is not available on OpenRouter | Week 2 runs could not use the planned rewriter | provider catalogues differ | runs use `meta-llama/llama-3.1-8b-instruct` via `.env`, code defaults unchanged; documented with the results |
| 2026-10-28 | The same v1 configuration measured p95 10.6 s, then 3.7 s two hours later | the first optimisation rows looked like −30% to −70% p95 wins that were mostly the provider getting faster | generation time depends on which OpenRouter provider serves the call and how busy it is | re-ran the baseline back to back with the final candidate; only back-to-back pairs are compared; lesson: measure the noise (we also found ±1.2 points of correctness between identical runs) before reading a delta |
| 2026-10-28 | Week 8 target (−50% p95 or cost) not met end to end | v2 is −24% p95, −3% cost | after making generation fast (−51%), the CPU cross-encoder (~1 s, ~3 s under 3 concurrent requests) is the tail, and every cheaper reranking setting lost 3–12 points of recall/correctness | kept the honest result; next lever is a faster reranker (GPU or distilled model) |
| 2026-10-28 | First push of the rebuilt history failed CI | red `main` for one run | an eval script added that day was never linted locally (import order) | fixed; lesson: run `ruff check librarian tests eval` before every push, as CONTRIBUTING says |

## What went well

* **Measuring retrieval and generation separately.** The ablation showed exactly what each stage adds
  (hybrid +4 points over BM25, reranker +5) and the false "I don't know" answers turned out to be retrieval
  misses, not generator mistakes. That told us where to work.
* **Gold passages as text, not chunk ids.** The same 120 questions scored five chunking variants and the
  full index without relabelling anything.
* **Abstention before the LLM.** A calibrated reranker threshold stops 13 of 16 out-of-scope questions with
  zero LLM cost and zero false refusals on the answerable ones.
* **Models as config.** Moving providers (Groq → OpenRouter), swapping the rewriter and pinning the
  generator's provider were all `.env` changes.

## What we would do differently

* Build the eval set **with the full corpus** from day one: the Week 1 seed set (docs only, 20 easy questions)
  gave a recall@5 of 0.90 that the real set brought down to 0.76, and one "unanswerable" label was wrong.
* **Repeat every latency measurement back to back** and run each configuration twice before reading a delta;
  we lost one round of optimisation runs to provider drift.
* Budget for the **reranker's CPU cost** at design time: it is the most valuable stage for quality and the
  biggest latency term once the LLM is fast.
* Deploy earlier: real-user logs and feedback are still missing, so the failure cases come from our own
  eval set only.

## What we learned

* A metric without its noise level is not a result: ±1.2 points of correctness and 3× latency drift were
  larger than several of the effects we were trying to measure.
* Retrieval quality, not the LLM, bounds answer quality: every wrong refusal we inspected was a retrieval miss.
* Cheaper is not free: the smaller generator halved cost but lost 5 points of correctness and 15 of faithfulness.
* Synthetic eval questions need as much review as hand-written ones: half of the LLM drafts were unusable.
