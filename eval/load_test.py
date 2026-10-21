"""End-to-end latency against a running service (local or deployed).

    python eval/load_test.py --url https://<space>.hf.space --n 30 --concurrency 3

Uses eval questions; mind the service rate limit (RATE_LIMIT_PER_MINUTE) and the LLM free tier.
"""

from __future__ import annotations

import concurrent.futures as cf
import time

import httpx
import typer
from common import load_questions, percentile, save_results


def main(url: str = "http://localhost:8000", n: int = 20, concurrency: int = 2):
    questions = [q["question"] for q in load_questions()][:n]

    def one(question: str) -> tuple[int, float]:
        t0 = time.perf_counter()
        r = httpx.post(f"{url.rstrip('/')}/api/ask", json={"question": question}, timeout=120)
        return r.status_code, (time.perf_counter() - t0) * 1000

    with cf.ThreadPoolExecutor(concurrency) as pool:
        results = list(pool.map(one, questions))
    ok = [ms for code, ms in results if code == 200]
    summary = {"url": url, "n": len(results), "ok": len(ok), "errors": len(results) - len(ok),
               "p50_ms": percentile(ok, 50), "p95_ms": percentile(ok, 95), "concurrency": concurrency}
    save_results("load_test", summary)
    print(summary)


if __name__ == "__main__":
    typer.run(main)
