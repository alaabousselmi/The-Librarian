"""Corpus statistics for the report: documents, tokens and chunks per source type.

Reads data/processed/documents.jsonl (and the chunk file of the default collection if it
exists) and writes docs/corpus.md.

    python eval/corpus_stats.py
"""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict

import typer
from common import ROOT

from librarian.chunking import count_tokens
from librarian.config import get_settings
from librarian.models import read_jsonl

LABEL = {"docs": "Docs pages", "discussion": "Discussions (answered)", "issue": "Issues (closed, with replies)"}


def main(collection: str = None):
    s = get_settings()
    docs = list(read_jsonl(s.processed_dir / "documents.jsonl"))
    by_type: dict[str, list[dict]] = defaultdict(list)
    for d in docs:
        by_type[d["source_type"]].append(d)
    chunk_path = s.processed_dir / f"chunks_{collection or s.collection}.jsonl"
    chunks = list(read_jsonl(chunk_path)) if chunk_path.exists() else []
    chunks_by_type = Counter(c["source_type"] for c in chunks)

    lines = ["# Corpus", "",
             f"Built with `librarian ingest` from `{s.fastapi_repo}` at ref `{s.fastapi_ref}` "
             "(docs) and the GitHub API (Discussions, issues).", "",
             "| Source | Documents | Tokens (cl100k) | Median tokens / doc | Chunks | Date range |",
             "|---|---|---|---|---|---|"]
    total_tokens = 0
    for t in ("docs", "discussion", "issue"):
        items = by_type.get(t, [])
        if not items:
            continue
        toks = [count_tokens(d["text"]) for d in items]
        total_tokens += sum(toks)
        dates = sorted(d["created_at"][:10] for d in items if d.get("created_at"))
        span = f"{dates[0]} → {dates[-1]}" if dates else "pinned release"
        lines.append(f"| {LABEL[t]} | {len(items):,} | {sum(toks):,} | {statistics.median(toks):,.0f} | "
                     f"{chunks_by_type.get(t, 0):,} | {span} |")
    lines.append(f"| **Total** | **{len(docs):,}** | **{total_tokens:,}** | | **{len(chunks):,}** | |")

    sections = Counter(d["section"] for d in by_type.get("discussion", []))
    roles = Counter(d["author"] for d in docs if d["source_type"] != "docs")
    lines += ["", f"Fetch limits: the {s.max_discussions:,} most recent Discussions (only answered ones kept: "
              f"ONLY_ANSWERED_DISCUSSIONS={s.only_answered_discussions}) and {s.max_issues} closed issues with replies, "
              "most-commented first."]
    lines += ["", f"Chunks: `{chunk_path.name}` ({s.chunk_strategy}, {s.chunk_size} tokens, "
              f"{s.chunk_overlap} overlap)." if chunks else "", "",
              "Discussion categories: " + ", ".join(f"{k} ({v})" for k, v in sections.most_common()), "",
              "Authors are stored as roles only: " + ", ".join(f"{k} ({v})" for k, v in roles.most_common()),
              "",
              "## Licence and permission", "",
              "* **Docs**: the FastAPI repository, documentation included, is MIT-licensed "
              "(© Sebastián Ramírez). We redistribute nothing: the corpus is rebuilt from source by "
              "`librarian build`, and answers link back to the original page.",
              "* **Discussions and issues**: public content on github.com, fetched through the official API "
              "under GitHub's terms. We store no usernames (authors are reduced to maintainer / contributor "
              "/ community), skip `fastapi-people.md`, and do not commit raw data (`data/` is gitignored).",
              ""]
    out = ROOT / "docs" / "corpus.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    typer.run(main)
