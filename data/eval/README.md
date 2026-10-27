# Eval set

`questions.jsonl`: 120 questions (104 answerable, 16 unanswerable). Format: see `eval/common.py`.

| Batch (`author`) | Rows | How it was made |
|---|---|---|
| `seed` | q001–q025 | hand-written in Week 1, checked against the docs (`verified: true`) |
| `batch-2` | q026–q059 | hand-written from the docs: tutorial and advanced pages the seed set did not cover, multi-part, code and "since which version" questions, 8 unanswerable |
| `batch-3` | q060–q077 | taken from real GitHub Discussions and issues that have a maintainer answer, plus one multi-part question mixing a discussion and a docs page, and 5 unanswerable |
| `llm:qwen/qwen3.8-27b` | q078–q120 | drafted by `eval/build_dataset.py` from random chunks (30 per source type), then reviewed: 43 of 87 kept |

Checks applied to every row:

* every gold passage is found in the cleaned source document (coverage 1.0 for hand-written rows,
  ≥ 0.9 for LLM drafts, where the model elided text with "…");
* unanswerable questions were grepped against the whole corpus: none of their topics has an answer in it
  (two first drafts, Express middleware order and React `useEffect`, were replaced because Discussions mention them);
* q023 (admin panel) was unanswerable with the docs-only corpus and became answerable once Discussions
  were ingested (discussion 13430 lists FastAdmin, Starlette-admin, SQLAdmin, Piccolo Admin); it is relabelled.

`candidates.jsonl` keeps all 87 LLM drafts with the review decision (`review`: keep / drop + reason).
Drop reasons: release-note trivia (who translated what, sponsors), the passage does not contain the answer,
duplicates of hand-written rows, a claim that contradicts the docs (CORS `"*"` with credentials), off-topic.

New rows are `verified: false` until a second teammate has checked the answer and passage against the
source (CONTRIBUTING.md). The eval scripts use all rows; `--verified-only` restricts to checked ones.
