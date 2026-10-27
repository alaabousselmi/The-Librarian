"""Generation eval: correctness, faithfulness, citation accuracy and "I don't know" behaviour,
plus end-to-end latency and cost per request.

The judge is a different model family (Qwen) from the generator (gpt-oss), to avoid a
model grading its own family. Validate the judge by hand-checking a sample (PLAN.md, Week 2).

    python eval/generation_eval.py --limit 20
    python eval/generation_eval.py --name after_top_k_4 --top-k 4     # Week 8 before/after runs
"""

from __future__ import annotations

import json
import time

import typer
from common import load_questions, percentile, save_results

from librarian.config import get_settings
from librarian.llm import LLM
from librarian.pipeline import AskOptions, Pipeline


class TokenPacer:
    """Stay under a provider's tokens-per-minute limit so measured latency is the system's,
    not time spent queued behind the free-tier quota (Groq free: 8k TPM for gpt-oss-120b)."""

    def __init__(self, tpm: int):
        self.tpm = tpm
        self.events: list[tuple[float, int]] = []
        self.estimate = 2500

    def wait(self) -> None:
        if self.tpm <= 0:
            return
        while True:
            now = time.time()
            self.events = [(t, n) for t, n in self.events if now - t < 60]
            if sum(n for _, n in self.events) + self.estimate <= self.tpm or not self.events:
                return
            time.sleep(max(60 - (now - self.events[0][0]), 0.5))

    def record(self, tokens: int) -> None:
        if tokens:
            self.events.append((time.time(), tokens))
            self.estimate = max(tokens, 1000)

JUDGE_SYSTEM = """You grade answers produced by a documentation assistant for the FastAPI framework.
You get: the question, a reference answer written by a human, the assistant's answer, and the
numbered sources the assistant cited.

1. correctness: compare the assistant's answer to the reference answer.
   1 = same key facts, no contradiction; 0.5 = partly correct or incomplete; 0 = wrong, contradicts,
   or says it does not know.
2. claims: split the assistant's answer into its factual claims (skip greetings and code-only lines).
   For each claim list the source numbers it cites, and decide whether those cited sources actually
   support it ("supported": true/false). A claim citing nothing is "supported": false.

Return only JSON:
{"correctness": 0|0.5|1, "reason": "...",
 "claims": [{"claim": "...", "citations": [1], "supported": true}]}"""


def cited_sources(result) -> str:
    return "\n\n".join(f"[{c.n}] {c.title}\n{h.chunk.text}"
                       for c in result.citations
                       for h in result.hits if h.chunk.chunk_id == c.chunk_id)


def judge(judge_llm: LLM, q: dict, answer: str, sources: str) -> dict:
    user = (f"Question: {q['question']}\n\nReference answer: {q['answer']}\n\n"
            f"Assistant answer:\n{answer}\n\nCited sources:\n{sources or '(none)'}")
    r = judge_llm.complete([{"role": "system", "content": JUDGE_SYSTEM}, {"role": "user", "content": user}],
                           max_tokens=1200, json_mode=True)
    try:
        verdict = json.loads(r.text)
    except json.JSONDecodeError:
        verdict = {"correctness": None, "claims": [], "reason": f"unparseable judge output: {r.text[:200]}"}
    verdict["_tokens"] = r.input_tokens + r.output_tokens
    return verdict


def main(name: str = "generation", limit: int = None, verified_only: bool = False,
         mode: str = None, rerank: bool = None, top_k: int = None, rewrite_mode: str = None,
         tpm: int = typer.Option(8000, help="provider tokens/minute limit to pace under (0 = no pacing)")):
    s = get_settings()
    pipe = Pipeline(s)
    judge_llm = LLM("judge", s)
    options = AskOptions(mode=mode, rerank=rerank, top_k=top_k, rewrite_mode=rewrite_mode)
    gen_pacer, judge_pacer = TokenPacer(tpm), TokenPacer(tpm)
    rows = []
    for i, q in enumerate(load_questions(only_verified=verified_only, limit=limit), 1):
        gen_pacer.wait()
        result = pipe.ask(q["question"], options=options)
        gen_pacer.record(int(result.usage["input_tokens"] + result.usage["output_tokens"]))
        row = {"id": q["id"], "category": q.get("category"), "answerable": q.get("answerable", True),
               "answer": result.answer, "abstained": result.abstained, "abstain_reason": result.abstain_reason,
               "citations": [c.chunk_id for c in result.citations], "total_ms": result.timings_ms["total_ms"],
               "timings_ms": result.timings_ms, **result.usage}
        if not row["answerable"]:
            row["correctness"] = 1.0 if result.abstained else 0.0
            row["claims"] = []
        elif result.abstained:
            row["correctness"], row["claims"] = 0.0, []
        else:
            judge_pacer.wait()
            row["cited_sources"] = cited_sources(result)
            verdict = judge(judge_llm, q, result.answer, row["cited_sources"])
            judge_pacer.record(verdict.pop("_tokens", 0))
            row["correctness"] = verdict.get("correctness")
            row["claims"] = verdict.get("claims", [])
            row["judge_reason"] = verdict.get("reason")
        rows.append(row)
        print(f"[{i}] {q['id']} correctness={row['correctness']} abstained={result.abstained} "
              f"{row['total_ms']:.0f}ms")

    answered = [r for r in rows if r["answerable"] and not r["abstained"]]
    claims = [c for r in answered for c in r["claims"]]
    cited = [c for c in claims if c.get("citations")]
    unans = [r for r in rows if not r["answerable"]]
    ans = [r for r in rows if r["answerable"]]
    graded = [r["correctness"] for r in rows if r["correctness"] is not None]
    lat = [r["total_ms"] for r in rows]
    summary = {
        "name": name, "n_questions": len(rows), "generator": s.generator_model, "judge": s.judge_model,
        "correctness": sum(graded) / len(graded) if graded else None,
        "faithfulness": sum(bool(c.get("supported")) for c in claims) / len(claims) if claims else None,
        "citation_accuracy": sum(bool(c.get("supported")) for c in cited) / len(cited) if cited else None,
        "uncited_claim_rate": 1 - len(cited) / len(claims) if claims else None,
        "idk_recall": sum(r["abstained"] for r in unans) / len(unans) if unans else None,
        "false_idk_rate": sum(r["abstained"] for r in ans) / len(ans) if ans else None,
        "p50_ms": percentile(lat, 50), "p95_ms": percentile(lat, 95),
        "avg_cost_usd": sum(r["cost_usd"] for r in rows) / len(rows) if rows else None,
        "avg_input_tokens": sum(r["input_tokens"] for r in rows) / len(rows) if rows else None,
        "config": {"mode": mode or s.retrieval_mode, "rerank": s.use_reranker if rerank is None else rerank,
                   "top_k": top_k or s.top_k, "rewrite": rewrite_mode or s.rewrite_mode},
    }
    print(save_results(name, summary, rows))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    typer.run(main)
