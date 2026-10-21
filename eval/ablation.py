"""Ablation: what do hybrid search and the reranker each add?

Runs the retrieval eval for every configuration on the same questions and writes
eval/results/ablation.md (the table that goes in the report).

    python eval/ablation.py                                   # 4 core configs on the default index
    python eval/ablation.py --collections librarian,librarian_fixed_400   # + chunking variants
    python eval/ablation.py --rewrite                         # also hybrid+rerank+rewrite (uses the LLM)
"""

from __future__ import annotations

import typer
from common import RESULTS, load_questions, markdown_table, save_results
from retrieval_eval import evaluate

from librarian.config import get_settings
from librarian.embeddings import Encoders
from librarian.llm import LLM
from librarian.retrieval import Retriever
from librarian.store import Store

CONFIGS = [
    ("BM25 only", "bm25", False),
    ("Dense only", "dense", False),
    ("Hybrid (RRF)", "hybrid", False),
    ("Hybrid + reranker", "hybrid", True),
]
COLUMNS = ["collection", "config", "recall@1", "recall@3", "recall@5", "recall@10", "mrr@10",
           "search_p50_ms", "search_p95_ms", "n_questions"]


def main(collections: str = None, rewrite_queries: bool = typer.Option(False, "--rewrite"),
         verified_only: bool = False, limit: int = None):
    s = get_settings()
    enc = Encoders(s)
    enc.warmup()  # model loading must not count as search latency
    questions = load_questions(only_verified=verified_only, limit=limit)
    table = []
    for coll in (collections.split(",") if collections else [s.collection]):
        retriever = Retriever(s, Store(s, enc, collection=coll), enc)
        configs = list(CONFIGS)
        if rewrite_queries:
            configs.append(("Hybrid + reranker + rewrite", "hybrid", True))
        for label, mode, rerank in configs:
            rewriter = LLM("rewriter", s) if "rewrite" in label else None
            summary, _ = evaluate(retriever, questions, mode, rerank, rewriter)
            table.append({"collection": coll, "config": label, **summary})
            print(f"{coll:>24} | {label:<28} recall@5={summary['recall@5']:.3f} mrr={summary['mrr@10']:.3f}")
    save_results("ablation", {"rows": table})
    md = "# Retrieval ablation\n\n" + markdown_table(table, COLUMNS) + "\n"
    (RESULTS / "ablation.md").write_text(md, encoding="utf-8")
    print("\n" + md)


if __name__ == "__main__":
    typer.run(main)
