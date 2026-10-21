# Postmortem

Written in Week 3. Blameless: describe what happened, why, and what we changed. A postmortem with no
problems loses points — log problems here **as they happen** during the three weeks.

## Incident / problem log

| Date | What went wrong | Impact | Root cause | Fix / lesson |
|---|---|---|---|---|
| 2026-10-21 | `<dfn title='…'>` tooltips with single quotes were left as raw HTML in the indexed text | noisy chunks on pages like dependencies-with-yield | regex only handled double quotes | fixed regex + unit test; lesson: inspect ingested text, not just counts |
| 2026-10-21 | One chunk was 2 530 tokens (budget 400) | a base64 image string in a code block dominated a chunk | code splitter only split between lines | truncate absurdly long lines; overlap can no longer push a chunk over budget; tests added |
| 2026-10-21 | Index had 2 296 points for 2 295 chunks | one stale chunk from the previous build was searchable | Qdrant embedded mode on Windows kept points across delete+create | `recreate()` now also deletes all points; lesson: assert count == chunks after indexing |
| 2026-10-21 | Generator `llama-3.3-70b-versatile` returned 404 model_not_found | no answers at all | Groq retired the model; the plan relied on a blog list | re-probed `/models`, moved to gpt-oss-120b / allam-2-7b / qwen3.8-27b; lesson: check the provider's live model list, models are config not code |
| 2026-10-21 | Multi-part question "enable CORS? and how to test?" answered only the CORS half | half of the answer was "I don't know" although the testing docs were retrieved | reranker scored all candidates against the full question, so the dominant part took all 6 slots | rerank each rewritten sub-query against its own candidates and interleave; regression test added |
| 2026-10-21 | Faithfulness 0.71 on the first generation eval | correct answers judged "uncited" | gpt-oss sometimes cites as `【2】` / `【2†L1-L3】`, our parser only knew `[2]` | normalise native citations before parsing; test added; lesson: read the judge's reasons before trusting a metric |
| 2026-10-21 | p50 latency 11 s in the first generation eval vs ~2 s by hand | latency numbers meaningless | free tier = 8 000 tokens/min for gpt-oss-120b; the SDK silently retried 429s | eval paces to the TPM limit; limits documented in design.md |
| 2026-10-21 | `librarian build` crashed inside Docker: PermissionError on `site-packages/data` | the README setup command did not work | data dir was derived from the package location, which is site-packages when installed non-editable | `DATA_DIR` env var, set in the Dockerfile; lesson: test the exact README commands, not just the dev setup |
| 2026-10-21 | include directives *inside* code fences were not resolved (7 cases, e.g. templates, JS clients) | code examples missing | loader skipped all lines in fences | resolve includes in fences too |

## What went well

## What we would do differently

## What we learned
