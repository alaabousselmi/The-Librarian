from types import SimpleNamespace

from fastapi.testclient import TestClient

from librarian.api.app import create_app
from librarian.generate import Citation
from librarian.pipeline import AskResult
from librarian.telemetry import Telemetry


class FakePipeline:
    def __init__(self):
        self.generator = SimpleNamespace(model="fake-model")
        self.store = SimpleNamespace(count=lambda: 10)
        self.encoders = SimpleNamespace(warmup=lambda: None)

    def ask(self, question, filters=None, options=None):
        return AskResult(
            request_id="req1", question=question, answer="Use `BackgroundTasks` [1].",
            citations=[Citation(1, "docs:bg#0", "docs:bg", "Background Tasks", "https://x/bg", "docs", "snippet")],
            abstained=False, abstain_reason=None, queries=[question], hits=[],
            timings_ms={"total_ms": 12.0}, usage={"input_tokens": 10, "output_tokens": 5, "cost_usd": 0.0},
        )


def client(tmp_path):
    app = create_app(pipeline=FakePipeline(), telemetry=Telemetry(str(tmp_path / "t.db")))
    return TestClient(app)


def test_ask_feedback_and_stats(tmp_path):
    with client(tmp_path) as c:
        r = c.post("/api/ask", json={"question": "How do I run code after the response?"})
        assert r.status_code == 200
        body = r.json()
        assert body["citations"][0]["url"] == "https://x/bg"
        assert "retrieved" not in body

        assert c.post("/api/feedback", json={"request_id": "req1", "rating": 1}).status_code == 200
        assert c.post("/api/feedback", json={"request_id": "nope", "rating": 1}).status_code == 404

        stats = c.get("/api/stats").json()
        assert stats["requests"] == 1 and stats["feedback_up"] == 1


def test_validation_and_health(tmp_path):
    with client(tmp_path) as c:
        assert c.get("/healthz").json() == {"status": "ok"}
        assert c.get("/readyz").status_code == 200
        assert c.post("/api/ask", json={"question": "x"}).status_code == 422
        assert c.get("/").status_code == 200
