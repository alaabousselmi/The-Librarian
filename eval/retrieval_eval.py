"""Retrieval eval: recall@k, MRR@10 and search latency for one retrieval configuration.

    python eval/retrieval_eval.py --mode hybrid --rerank
    python eval/retrieval_eval.py --mode bm25 --no-rerank --collection librarian_fixed_400

No LLM is called unless --rewrite is given, so this runs offline and free.
"""

from __future__ import annotations

import time

import typer
from common import is_hit, load_questions, percentile, save_results

from librarian.config import get_settings
from librarian.embeddings import Encoders
from librarian.llm import LLM
from librarian.retrieval import Retriever
from librarian.rewrite import rewrite
from librarian.store import Store

KS = (1, 3, 5, 10)


def evaluate(retriever: Retriever, questions: list[dict], mode: str, rerank: bool,
             rewriter: LLM | None = None) -> tuple[dict, list[dict]]:
    rows, latencies = [], []
    for q in questions:
        if not q.get("answerable", True) or not q.get("sources"):
            continue
        queries = rewrite(q["question"], rewriter, "auto")[0] if rewriter else [q["question"]]
        t0 = time.perf_counter()
        res = retriever.retrieve(queries, mode=mode, rerank=rerank, top_k=max(KS), rerank_query=q["question"])
        latencies.append((time.perf_counter() - t0) * 1000)
        chunks = [h.chunk for h in res.hits]
        first_hit = next((i for i, c in enumerate(chunks, 1) if any(is_hit(c, s) for s in q["sources"])), None)
        row = {"id": q["id"], "first_hit_rank": first_hit, "retrieved": [c.chunk_id for c in chunks]}
        for k in KS:
            found = sum(any(is_hit(c, s) for c in chunks[:k]) for s in q["sources"])
            row[f"recall@{k}"] = found / len(q["sources"])
        row["rr"] = 1 / first_hit if first_hit else 0.0
        rows.append(row)
    n = len(rows) or 1
    summary = {f"recall@{k}": sum(r[f"recall@{k}"] for r in rows) / n for k in KS}
    summary.update({
        "mrr@10": sum(r["rr"] for r in rows) / n,
        "search_p50_ms": percentile(latencies, 50),
        "search_p95_ms": percentile(latencies, 95),
        "n_questions": len(rows),
    })
    return summary, rows


def main(mode: str = "hybrid", rerank: bool = True, collection: str = None, rewrite_queries: bool = typer.Option(False, "--rewrite"),
         verified_only: bool = False, limit: int = None):
    s = get_settings()
    enc = Encoders(s)
    enc.warmup()  # model loading must not count as search latency
    retriever = Retriever(s, Store(s, enc, collection=collection), enc)
    questions = load_questions(only_verified=verified_only, limit=limit)
    summary, rows = evaluate(retriever, questions, mode, rerank, LLM("rewriter", s) if rewrite_queries else None)
    summary.update({"mode": mode, "rerank": rerank, "rewrite": rewrite_queries, "collection": collection or s.collection})
    name = f"retrieval_{collection or s.collection}_{mode}{'_rerank' if rerank else ''}"
    print(save_results(name, summary, rows))
    for k, v in summary.items():
        print(f"{k:>16}: {v:.3f}" if isinstance(v, float) else f"{k:>16}: {v}")


if __name__ == "__main__":
    typer.run(main)
