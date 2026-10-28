"""End-to-end latency against a running service (local or deployed).

    python eval/load_test.py --url https://<space>.hf.space --n 30 --concurrency 3

Uses eval questions; mind the service rate limit (RATE_LIMIT_PER_MINUTE) and the LLM free tier.
For a local run start the server with RATE_LIMIT_PER_MINUTE=0, otherwise most requests are 429s.
"""

from __future__ import annotations

import concurrent.futures as cf
import time
from collections import Counter

import httpx
import typer
from common import RESULTS, load_questions, percentile, save_results


def main(url: str = "http://localhost:8000", n: int = 20, concurrency: int = 2, name: str = "load_test"):
    questions = [q["question"] for q in load_questions()][:n]

    def one(question: str) -> tuple[int, float, dict]:
        t0 = time.perf_counter()
        try:
            r = httpx.post(f"{url.rstrip('/')}/api/ask", json={"question": question}, timeout=120)
            code, body = r.status_code, (r.json() if r.status_code == 200 else {})
        except httpx.HTTPError:
            code, body = 0, {}
        return code, (time.perf_counter() - t0) * 1000, body

    t_start = time.perf_counter()
    with cf.ThreadPoolExecutor(concurrency) as pool:
        results = list(pool.map(one, questions))
    wall_s = time.perf_counter() - t_start
    ok = [ms for code, ms, _ in results if code == 200]
    server = [b["timings_ms"]["total_ms"] for code, _, b in results if code == 200]
    summary = {"url": url, "n": len(results), "concurrency": concurrency,
               "status": dict(Counter(code for code, _, _ in results)),
               "throughput_rps": round(len(results) / wall_s, 2),
               "p50_ms": percentile(ok, 50), "p95_ms": percentile(ok, 95), "max_ms": round(max(ok), 1) if ok else None,
               "server_p50_ms": percentile(server, 50), "server_p95_ms": percentile(server, 95)}
    save_results(name, summary)
    md = ["# Load test", "", f"`{url}` · {len(results)} questions · concurrency {concurrency}", "",
          "| metric | value |", "|---|---|"]
    md += [f"| {k} | {v} |" for k, v in summary.items() if k not in ("url", "n", "concurrency")]
    (RESULTS / f"{name}.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(summary)


if __name__ == "__main__":
    typer.run(main)
