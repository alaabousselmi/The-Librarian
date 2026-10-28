# Load test

`http://localhost:8000` · 30 questions · concurrency 3

| metric | value |
|---|---|
| status | {200: 30} |
| throughput_rps | 0.77 |
| p50_ms | 3836.0 |
| p95_ms | 4450.0 |
| max_ms | 4810.7 |
| server_p50_ms | 3766.8 |
| server_p95_ms | 4431.8 |

Run locally (laptop CPU, Qdrant in Docker, v2 config, generator on Groq via OpenRouter), `RATE_LIMIT_PER_MINUTE=0`.
Server-side breakdown from telemetry (30 requests): search p50 78 ms, **rerank p50 3 068 ms** (vs ~950 ms
with one request at a time: three cross-encoders share the CPU), generation p50 657 ms / p95 1 384 ms.
Throughput is bounded by the CPU reranker at ~1 request/s on this machine.
