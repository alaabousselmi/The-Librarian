"""Request log + user feedback in SQLite.

This is the source for the "Service" metrics in the report: p50/p95 latency,
cost per request, abstention rate and real-user feedback.
"""

from __future__ import annotations

import json
import sqlite3
import statistics
import threading
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS requests (
    request_id TEXT PRIMARY KEY,
    ts REAL NOT NULL,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    abstained INTEGER NOT NULL,
    abstain_reason TEXT,
    n_citations INTEGER NOT NULL,
    cited_chunks TEXT NOT NULL,
    total_ms REAL NOT NULL,
    timings TEXT NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    cost_usd REAL NOT NULL,
    model TEXT NOT NULL,
    config TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id TEXT NOT NULL,
    ts REAL NOT NULL,
    rating INTEGER NOT NULL,      -- +1 / -1
    comment TEXT
);
"""


class Telemetry:
    def __init__(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self._conn.executescript(SCHEMA)

    def log_request(self, result, model: str, config: dict) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO requests VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (result.request_id, time.time(), result.question, result.answer, int(result.abstained),
                 result.abstain_reason, len(result.citations),
                 json.dumps([c.chunk_id for c in result.citations]),
                 result.timings_ms.get("total_ms", 0), json.dumps(result.timings_ms),
                 int(result.usage.get("input_tokens", 0)), int(result.usage.get("output_tokens", 0)),
                 float(result.usage.get("cost_usd", 0)), model, json.dumps(config)),
            )
            self._conn.commit()

    def add_feedback(self, request_id: str, rating: int, comment: str | None) -> bool:
        with self._lock:
            exists = self._conn.execute("SELECT 1 FROM requests WHERE request_id=?", (request_id,)).fetchone()
            if not exists:
                return False
            self._conn.execute("INSERT INTO feedback (request_id, ts, rating, comment) VALUES (?,?,?,?)",
                               (request_id, time.time(), rating, comment))
            self._conn.commit()
            return True

    def stats(self, since_s: float | None = None) -> dict:
        since = time.time() - since_s if since_s else 0
        with self._lock:
            rows = self._conn.execute(
                "SELECT total_ms, cost_usd, abstained FROM requests WHERE ts >= ?", (since,)).fetchall()
            fb = self._conn.execute(
                "SELECT SUM(rating > 0), SUM(rating < 0) FROM feedback WHERE ts >= ?", (since,)).fetchone()
        lat = sorted(r[0] for r in rows)

        def pct(p: float) -> float | None:
            if not lat:
                return None
            return round(statistics.quantiles(lat, n=100, method="inclusive")[p - 1], 1) if len(lat) > 1 else lat[0]

        return {
            "requests": len(rows),
            "p50_ms": pct(50),
            "p95_ms": pct(95),
            "avg_cost_usd": round(sum(r[1] for r in rows) / len(rows), 6) if rows else None,
            "abstention_rate": round(sum(r[2] for r in rows) / len(rows), 3) if rows else None,
            "feedback_up": fb[0] or 0,
            "feedback_down": fb[1] or 0,
        }
