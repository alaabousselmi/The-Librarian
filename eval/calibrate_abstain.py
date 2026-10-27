"""Calibrate ABSTAIN_THRESHOLD: the best-chunk rerank logit below which we answer
"I don't know" without calling the LLM.

For every eval question we record the top rerank score, then sweep thresholds and report
how many unanswerable questions are caught (IDK recall) against how many answerable ones
are wrongly refused (false IDK). A false IDK costs more than a missed one (the generator
can still abstain on its own), so we pick the highest threshold with false IDK <= --max-false.

    python eval/calibrate_abstain.py
"""

from __future__ import annotations

import typer
from common import RESULTS, load_questions, save_results

from librarian.config import get_settings
from librarian.embeddings import Encoders
from librarian.retrieval import Retriever
from librarian.store import Store


def main(max_false: float = typer.Option(0.02, help="max share of answerable questions refused")):
    s = get_settings()
    enc = Encoders(s)
    retriever = Retriever(s, Store(s, enc), enc)
    rows = []
    for q in load_questions():
        res = retriever.retrieve([q["question"]], mode="hybrid", rerank=True)
        rows.append({"id": q["id"], "answerable": q.get("answerable", True),
                     "top_score": res.hits[0].score if res.hits else float("-inf")})

    ans = [r["top_score"] for r in rows if r["answerable"]]
    unans = [r["top_score"] for r in rows if not r["answerable"]]
    sweep = []
    for t10 in range(-120, 61, 5):
        t = t10 / 10
        sweep.append({"threshold": t,
                      "idk_recall": sum(x < t for x in unans) / len(unans),
                      "false_idk": sum(x < t for x in ans) / len(ans)})
    ok = [r for r in sweep if r["false_idk"] <= max_false]
    best = max(ok, key=lambda r: (r["idk_recall"], r["threshold"])) if ok else sweep[0]
    # among equally good thresholds keep the lowest, i.e. the furthest from the answerable ones
    best = min((r for r in ok if r["idk_recall"] == best["idk_recall"]), key=lambda r: r["threshold"],
               default=best)

    lines = ["# Abstention threshold calibration", "",
             f"{len(ans)} answerable, {len(unans)} unanswerable questions; score = top cross-encoder logit "
             f"(`{s.rerank_model}`).", "",
             f"Answerable top score: min {min(ans):.2f}, 5th pct {sorted(ans)[len(ans) // 20]:.2f}. "
             f"Unanswerable top score: min {min(unans):.2f}, max {max(unans):.2f}.", "",
             "| threshold | IDK recall (no LLM call) | false IDK |", "|---|---|---|"]
    for r in sweep:
        if r["idk_recall"] or r["false_idk"]:
            mark = " ← chosen" if r is best else ""
            lines.append(f"| {r['threshold']:.1f} | {r['idk_recall']:.2f} | {r['false_idk']:.2f}{mark} |")
    lines += ["", f"Chosen: **ABSTAIN_THRESHOLD={best['threshold']}** (false IDK ≤ {max_false:.0%}). "
              "Unanswerable questions above it are left to the generator's own \"I don't know\"."]
    (RESULTS / "abstain_calibration.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    save_results("abstain_calibration", {"chosen": best, "sweep": sweep}, rows)
    print("\n".join(lines))


if __name__ == "__main__":
    typer.run(main)
