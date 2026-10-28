"""Cost model: cost per request today and at 100x traffic, from measured eval runs.

Every number comes from a generation-eval run (eval/results/<run>.json + runs/<run>-*.jsonl):
tokens per request are measured, prices are the list prices in librarian/llm.py.

    python eval/cost_model.py --run baseline_v1 --after optimised_v2 --per-day 100
"""

from __future__ import annotations

import glob
import json
import statistics
from pathlib import Path

import typer
from common import RESULTS, ROOT

from librarian.llm import PRICES

# Groq free tier for the generator (measured from response headers, see design.md §9).
FREE_TPM, FREE_RPD = 8_000, 1_000


def load(run: str) -> tuple[dict, list[dict]]:
    summary = json.loads((RESULTS / f"{run}.json").read_text(encoding="utf-8"))
    files = sorted(glob.glob(str(RESULTS / "runs" / f"{run}-*.jsonl")))
    rows = [json.loads(line) for line in Path(files[-1]).read_text(encoding="utf-8").splitlines()] if files else []
    return summary, rows


def profile(run: str) -> dict:
    summary, rows = load(run)
    answered = [r for r in rows if r["llm_calls"] > 0]
    return {
        "run": run,
        "generator": summary["generator"],
        "n": len(rows),
        "llm_share": len(answered) / len(rows),
        "rewrite_share": sum(r["llm_calls"] > 1 for r in rows) / len(rows),
        "in_tokens": statistics.mean(r["input_tokens"] for r in rows),
        "out_tokens": statistics.mean(r["output_tokens"] for r in rows),
        "cost": statistics.mean(r["cost_usd"] for r in rows),
        "rerank_ms": statistics.median(r["timings_ms"].get("rerank_ms", 0) for r in rows),
        "p95_ms": summary["p95_ms"],
    }


def scenario(p: dict, per_day: int) -> dict:
    tokens = p["in_tokens"] + p["out_tokens"]  # per question, abstentions (0 tokens) included
    llm_requests = per_day * p["llm_share"]
    # busiest minute: assume 10% of the day's traffic lands in one hour, spread evenly
    peak_per_min = per_day * 0.10 / 60
    return {
        "per_day": per_day,
        "cost_day": per_day * p["cost"],
        "cost_month": per_day * p["cost"] * 30,
        "free_tier_ok": llm_requests <= FREE_RPD and peak_per_min * tokens <= FREE_TPM,
        "peak_per_min": peak_per_min,
        "free_max_per_min": FREE_TPM / tokens,
        "rerank_cpu_s_peak": peak_per_min / 60 * p["rerank_ms"] / 1000,
    }


def table(profiles: list[dict], per_day: int) -> list[str]:
    head = "| | " + " | ".join(p["run"] for p in profiles) + " |"
    lines = [head, "|---|" + "---|" * len(profiles)]

    def row(label, fn):
        lines.append(f"| {label} | " + " | ".join(fn(p) for p in profiles) + " |")

    row("generator", lambda p: f"`{p['generator']}`")
    row("questions in run", lambda p: str(p["n"]))
    row("requests that call an LLM", lambda p: f"{p['llm_share']:.0%}")
    row("requests that also rewrite", lambda p: f"{p['rewrite_share']:.0%}")
    row("avg input / output tokens", lambda p: f"{p['in_tokens']:,.0f} / {p['out_tokens']:,.0f}")
    row("**cost / request** (list price)", lambda p: f"**${p['cost']:.6f}**")
    row("cost / 1,000 requests", lambda p: f"${p['cost'] * 1000:.3f}")
    for mult, label in ((1, "today"), (100, "100×")):
        sc = [scenario(p, per_day * mult) for p in profiles]
        lines.append(f"| **{label}: {per_day * mult:,} questions/day** | " + " | ".join("" for _ in profiles) + " |")
        lines.append("| cost / day · month | " + " | ".join(
            f"${s['cost_day']:.2f} · ${s['cost_month']:.2f}" for s in sc) + " |")
        lines.append("| fits Groq free tier? | " + " | ".join(
            ("yes" if s["free_tier_ok"] else f"no (peak {s['peak_per_min']:.0f}/min vs {s['free_max_per_min']:.1f}/min)")
            for s in sc) + " |")
        lines.append("| reranker CPU at peak | " + " | ".join(
            f"{s['rerank_cpu_s_peak']:.2f} cores" for s in sc) + " |")
    return lines


def main(run: str = "baseline_v1", after: str = None, per_day: int = 100):
    profiles = [profile(run)] + ([profile(after)] if after else [])
    p = profiles[-1]
    lines = [
        "# Cost model", "",
        f"Measured on the {p['n']}-question eval set. Prices: list price per 1M tokens (input, output) from "
        "`librarian/llm.py`: " + ", ".join(f"`{m}` ${i:.3f} / ${o:.2f}" for m, (i, o) in PRICES.items()) + ".",
        "Embeddings, BM25 and the reranker run locally on CPU, so they cost CPU time, not money.", "",
        f"\"Today\" = {per_day} questions/day (the Week 2 target of ~100 questions from real users); "
        "peak = 10% of a day's traffic in one hour.", "",
        *table(profiles, per_day), "",
        "## Reading it", "",
        f"* **Today** the LLM bill is ${per_day * p['cost'] * 30:.2f}/month at list price, and $0 on the free tier, "
        "which is the binding constraint: "
        f"{FREE_TPM:,} tokens/min and {FREE_RPD:,} requests/day for the generator, i.e. "
        f"~{FREE_TPM / (p['in_tokens'] + p['out_tokens']):.1f} questions/min.",
        "* **At 100×** the free tier no longer fits (requests/day and tokens/min), so the generator moves to the "
        "paid tier of the same provider: the cost is the 100× row, and nothing else in the system changes "
        "(models are config).",
        "* Hosting: one CPU container (Hugging Face Spaces free tier, 2 vCPU) and Qdrant Cloud free tier (1 GB). "
        "The index is 19 650 points, 110 MB on disk in Qdrant (measured), and does not grow with traffic. "
        "The reranker is the only CPU-heavy step; the table shows the cores it needs at peak.",
        "* Not included: eval runs (judge tokens), which are a one-off per experiment, not per user request.", "",
    ]
    out = ROOT / "docs" / "cost_model.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    typer.run(main)
