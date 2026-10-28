"""Validate the LLM judge the way Project 1 did: agreement with humans, plus stability.

    python eval/judge_check.py sheet  --n 20      # export a sample of judged answers for hand grading
    python eval/judge_check.py score              # human vs judge, once the sheet is filled in
    python eval/judge_check.py repeat --n 40      # judge vs itself (same answers, judged twice)

The sheet is data/eval/judge_check.csv. Fill `human_correctness` with 0, 0.5 or 1 using the
same rubric as the judge (JUDGE_SYSTEM in generation_eval.py) without looking at the judge's
grade first. Agreement uses the P1 statistics (eval/agreement.py).
"""

from __future__ import annotations

import csv
import glob
import json
import random

import typer
from agreement import exact_pct, matrix_rows, quadratic_weighted_kappa, to_cat
from common import RESULTS, ROOT, load_questions, save_results
from generation_eval import judge

from librarian.config import get_settings
from librarian.llm import LLM

app = typer.Typer(no_args_is_help=True)
SHEET = ROOT / "data" / "eval" / "judge_check.csv"
FIELDS = ["id", "question", "reference_answer", "assistant_answer", "cited_sources",
          "human_correctness", "notes", "judge_correctness"]


def newest_run(name: str) -> list[dict]:
    files = sorted(glob.glob(str(RESULTS / "runs" / f"{name}-*.jsonl")))
    if not files:
        raise typer.Exit(f"no run for '{name}' in eval/results/runs: run generation_eval.py first")
    return [json.loads(line) for line in open(files[-1], encoding="utf-8") if line.strip()]


def judged(rows: list[dict]) -> list[dict]:
    return [r for r in rows if r["answerable"] and not r["abstained"] and r.get("correctness") is not None
            and "cited_sources" in r]


def report(title: str, pairs: list[tuple[int, int]]) -> list[str]:
    out = [f"### {title}", "", f"n = {len(pairs)} · exact agreement **{exact_pct(pairs):.1f}%** · "
           f"quadratic weighted kappa **{quadratic_weighted_kappa(pairs):+.3f}**", "",
           "| rows \\ cols | 0 | 0.5 | 1 |", "|---|---|---|---|"]
    for label, cells in zip(["0", "0.5", "1"], matrix_rows(pairs), strict=True):
        out.append(f"| **{label}** | " + " | ".join(f"{n}" for n, _ in cells) + " |")
    return out + [""]


@app.command()
def sheet(run: str = "generation", n: int = 20, seed: int = 7):
    """Export a random sample of judged answers for hand grading."""
    questions = {q["id"]: q for q in load_questions()}
    rows = judged(newest_run(run))
    sample = random.Random(seed).sample(rows, min(n, len(rows)))
    with SHEET.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, FIELDS)
        w.writeheader()
        for r in sample:
            q = questions[r["id"]]
            w.writerow({"id": r["id"], "question": q["question"], "reference_answer": q["answer"],
                        "assistant_answer": r["answer"], "cited_sources": r["cited_sources"],
                        "human_correctness": "", "notes": "", "judge_correctness": r["correctness"]})
    print(f"wrote {len(sample)} rows to {SHEET} — grade them before looking at judge_correctness")


@app.command()
def score():
    """Human vs judge agreement on the filled-in sheet."""
    with SHEET.open(encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["human_correctness"].strip()]
    if not rows:
        raise typer.Exit(f"no human grades in {SHEET} yet")
    pairs = [(to_cat(float(r["human_correctness"])), to_cat(float(r["judge_correctness"]))) for r in rows]
    md = "\n".join(report("Human (rows) vs judge (columns)", pairs))
    (RESULTS / "judge_check.md").write_text("# Judge check: human vs judge\n\n" + md, encoding="utf-8")
    print(md)


@app.command()
def repeat(run: str = "generation", n: int = 40, seed: int = 7):
    """Judge the same answers a second time: a judge that disagrees with itself cannot be trusted."""
    s = get_settings()
    judge_llm = LLM("judge", s)
    questions = {q["id"]: q for q in load_questions()}
    rows = judged(newest_run(run))
    sample = random.Random(seed).sample(rows, min(n, len(rows)))
    pairs, out_rows = [], []
    for r in sample:
        v = judge(judge_llm, questions[r["id"]], r["answer"], r["cited_sources"])
        if v.get("correctness") is None:
            continue
        pairs.append((to_cat(r["correctness"]), to_cat(v["correctness"])))
        out_rows.append({"id": r["id"], "first": r["correctness"], "second": v["correctness"]})
    md = "\n".join(report(f"Judge run 1 (rows) vs judge run 2 (columns), `{s.judge_model}`", pairs))
    save_results("judge_repeat", {"n": len(pairs), "exact_pct": exact_pct(pairs),
                                  "qwk": quadratic_weighted_kappa(pairs)}, out_rows)
    (RESULTS / "judge_repeat.md").write_text("# Judge stability\n\n" + md, encoding="utf-8")
    print(md)


if __name__ == "__main__":
    app()
