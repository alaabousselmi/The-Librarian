"""Chunking experiment: same retrieval pipeline, different chunk strategy / size / overlap.

Embedding the full corpus takes ~15 min per configuration on a laptop CPU, so the grid
runs on the docs subset (146 pages) and is scored on the questions whose gold sources are
all docs pages. Build one collection per configuration first:

    librarian index --sources docs --strategy markdown --size 200 --overlap 60 --collection docs_md_200_60
    ...
    python eval/chunking_eval.py --collections docs_md_200_60,docs_md_400_60,...
"""

from __future__ import annotations

import statistics

import typer
from common import RESULTS, load_questions, markdown_table, save_results
from retrieval_eval import evaluate

from librarian.config import get_settings
from librarian.embeddings import Encoders
from librarian.models import read_jsonl
from librarian.retrieval import Retriever
from librarian.store import Store

COLUMNS = ["collection", "chunks", "mean_tokens", "config", "recall@1", "recall@5", "recall@10", "mrr@10",
           "search_p50_ms", "n_questions"]


def main(collections: str = typer.Option(..., help="comma-separated collection names"), rerank_too: bool = True):
    s = get_settings()
    enc = Encoders(s)
    enc.warmup()
    questions = [q for q in load_questions()
                 if q.get("answerable", True) and q["sources"]
                 and all(src["doc_id"].startswith("docs:") for src in q["sources"])]
    table = []
    for coll in collections.split(","):
        chunks = list(read_jsonl(s.processed_dir / f"chunks_{coll}.jsonl"))
        info = {"collection": coll, "chunks": len(chunks),
                "mean_tokens": round(statistics.mean(c["n_tokens"] for c in chunks))}
        retriever = Retriever(s, Store(s, enc, collection=coll), enc)
        configs = [("Dense only", "dense", False), ("Hybrid (RRF)", "hybrid", False)]
        if rerank_too:
            configs.append(("Hybrid + reranker", "hybrid", True))
        for label, mode, rerank in configs:
            summary, _ = evaluate(retriever, questions, mode, rerank)
            table.append({**info, "config": label, **summary})
            print(f"{coll:>18} | {label:<18} recall@5={summary['recall@5']:.3f} mrr={summary['mrr@10']:.3f}")
    save_results("chunking", {"rows": table})
    md = ("# Chunking experiment (docs subset)\n\n"
          f"{len(questions)} answerable questions whose gold sources are docs pages; "
          "a hit = chunk from the gold page containing ≥ 60% of the gold passage.\n\n"
          + markdown_table(table, COLUMNS) + "\n")
    (RESULTS / "chunking.md").write_text(md, encoding="utf-8")
    print("\n" + md)


if __name__ == "__main__":
    typer.run(main)
