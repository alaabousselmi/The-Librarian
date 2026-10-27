# Corpus

Built with `librarian ingest` from `fastapi/fastapi` at ref `0.162.0` (docs) and the GitHub API (Discussions, issues).

| Source | Documents | Tokens (cl100k) | Median tokens / doc | Chunks | Date range |
|---|---|---|---|---|---|
| Docs pages | 146 | 454,456 | 1,088 | 2,325 | pinned release |
| Discussions (answered) | 993 | 1,132,079 | 875 | 12,214 | 2023-09-03 → 2026-10-22 |
| Issues (closed, with replies) | 400 | 646,025 | 1,359 | 5,111 | 2019-01-24 → 2025-09-30 |
| **Total** | **1,539** | **2,232,560** | | **19,650** | |

Fetch limits: the 2,000 most recent Discussions (only answered ones kept: ONLY_ANSWERED_DISCUSSIONS=True) and 400 closed issues with replies, most-commented first.

Chunks: `chunks_librarian.jsonl` (markdown, 400 tokens, 60 overlap).

Discussion categories: Questions (993)

Authors are stored as roles only: community (1303), contributor (74), maintainer (16)

## Licence and permission

* **Docs**: the FastAPI repository, documentation included, is MIT-licensed (© Sebastián Ramírez). We redistribute nothing: the corpus is rebuilt from source by `librarian build`, and answers link back to the original page.
* **Discussions and issues**: public content on github.com, fetched through the official API under GitHub's terms. We store no usernames (authors are reduced to maintainer / contributor / community), skip `fastapi-people.md`, and do not commit raw data (`data/` is gitignored).
