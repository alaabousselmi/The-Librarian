"""Draft eval candidates from the corpus, for HUMAN review.

Samples chunks (stratified by source type), asks an LLM for a realistic user question,
a reference answer and an exact supporting quote, and keeps only candidates whose quote
really appears in the chunk. Output: data/eval/candidates.jsonl with "verified": false.

A teammate must then read each candidate against the source, fix or drop it, set
"verified": true and move it to data/eval/questions.jsonl. Synthetic questions are
easier than real ones — mix in real questions from users and from GitHub Discussions.

    python eval/build_dataset.py --n 60 --role judge
"""

from __future__ import annotations

import json
import random
from collections import defaultdict

import typer
from common import ROOT, passage_coverage

from librarian.config import get_settings
from librarian.llm import LLM
from librarian.models import read_jsonl

PROMPT = """Here is a passage from the FastAPI documentation / community Q&A.

Write ONE question a real FastAPI developer might ask that this passage answers.
The question must be answerable from the passage alone, must not quote it, and should sound
natural (not "according to the passage...").

Return JSON: {"question": "...", "answer": "short reference answer",
"quote": "an exact sentence or two copied verbatim from the passage that supports the answer"}

Passage:
"""


def main(n: int = 60, role: str = "judge", seed: int = 7, collection: str = None):
    s = get_settings()
    llm = LLM(role, s)
    chunks = list(read_jsonl(s.processed_dir / f"chunks_{collection or s.collection}.jsonl"))
    by_type = defaultdict(list)
    for c in chunks:
        if c["n_tokens"] >= 80:
            by_type[c["source_type"]].append(c)
    rng = random.Random(seed)
    per_type = max(n // max(len(by_type), 1), 1)
    sample = [c for items in by_type.values() for c in rng.sample(items, min(per_type, len(items)))]

    out_path = ROOT / "data" / "eval" / "candidates.jsonl"
    kept = 0
    with out_path.open("a", encoding="utf-8") as f:
        for c in sample:
            try:
                r = llm.complete([{"role": "user", "content": PROMPT + c["text"]}], max_tokens=500, json_mode=True)
                cand = json.loads(r.text)
            except Exception as exc:
                print("skip:", exc)
                continue
            if passage_coverage(cand.get("quote", ""), c["text"]) < 0.9:
                continue  # the model paraphrased instead of quoting: unusable as gold
            kept += 1
            f.write(json.dumps({
                "id": f"cand-{c['chunk_id']}",
                "question": cand["question"], "answer": cand["answer"],
                "sources": [{"doc_id": c["doc_id"], "passage": cand["quote"]}],
                "answerable": True, "category": c["source_type"], "verified": False,
                "author": f"llm:{llm.model}",
            }, ensure_ascii=False) + "\n")
    print(f"kept {kept}/{len(sample)} candidates -> {out_path}")


if __name__ == "__main__":
    typer.run(main)
