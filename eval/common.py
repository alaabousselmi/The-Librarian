"""Shared helpers for the eval scripts.

Eval question format (one JSON object per line in data/eval/questions.jsonl):

    {
      "id": "q001",
      "question": "How do I declare an optional query parameter?",
      "answer": "Give it a default of None ...",          # reference answer
      "sources": [{"doc_id": "docs:tutorial/query-params",
                   "passage": "The same way, you can declare optional query parameters, ..."}],
      "answerable": true,          # false => the right output is "I don't know"
      "category": "docs",          # docs | discussion | issue | multi-part | code | version | unanswerable
      "verified": true,            # a teammate checked answer + passage against the source
      "author": "A"
    }

Gold passages are stored as *text*, not chunk ids, so the same test set stays valid
when the chunking changes (chunking is one of the things we experiment with).
A retrieved chunk counts as a hit if it comes from the gold document and contains
most of the gold passage.
"""

from __future__ import annotations

import json
import re
import statistics
import sys
import time
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

QUESTIONS = ROOT / "data" / "eval" / "questions.jsonl"
RESULTS = ROOT / "eval" / "results"


def load_questions(path: Path = QUESTIONS, only_verified: bool = False, limit: int | None = None) -> list[dict]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if only_verified:
        rows = [r for r in rows if r.get("verified")]
    return rows[:limit] if limit else rows


def _norm(text: str) -> str:
    text = re.sub(r"[`*_#>]", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def passage_coverage(passage: str, chunk_text: str) -> float:
    """Fraction of the gold passage's characters found (in order) in the chunk."""
    p, c = _norm(passage), _norm(chunk_text)
    if not p:
        return 0.0
    if p in c:
        return 1.0
    sm = SequenceMatcher(None, p, c, autojunk=False)
    return sum(b.size for b in sm.get_matching_blocks()) / len(p)


def is_hit(chunk, source: dict, threshold: float = 0.6) -> bool:
    return chunk.doc_id == source["doc_id"] and passage_coverage(source["passage"], chunk.text) >= threshold


def percentile(values: list[float], p: int) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return round(values[0], 1)
    return round(statistics.quantiles(values, n=100, method="inclusive")[p - 1], 1)


def save_results(name: str, summary: dict, rows: list[dict] | None = None) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    RESULTS.mkdir(parents=True, exist_ok=True)
    out = RESULTS / f"{name}.json"
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    if rows is not None:
        run_dir = RESULTS / "runs"
        run_dir.mkdir(parents=True, exist_ok=True)
        with (run_dir / f"{name}-{stamp}.jsonl").open("w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return out


def markdown_table(rows: list[dict], columns: list[str]) -> str:
    def fmt(v):
        return f"{v:.3f}" if isinstance(v, float) else ("" if v is None else str(v))

    lines = ["| " + " | ".join(columns) + " |", "|" + "---|" * len(columns)]
    lines += ["| " + " | ".join(fmt(r.get(c)) for c in columns) + " |" for r in rows]
    return "\n".join(lines)
