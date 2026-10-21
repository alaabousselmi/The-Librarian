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
