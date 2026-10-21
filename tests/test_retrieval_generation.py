from librarian.generate import IDK, generate, is_abstention, parse_citations
from librarian.llm import LLMResult
from librarian.models import Chunk
from librarian.retrieval import Hit, rrf
from librarian.rewrite import needs_rewrite


def chunk(i: int) -> Chunk:
    return Chunk(chunk_id=f"docs:p#{i}", doc_id="docs:p", source_type="docs", title=f"T{i}",
                 url=f"https://x/{i}", heading_path=[f"T{i}"], text=f"text {i}", position=i, n_tokens=2)


def test_rrf_rewards_agreement():
    a, b, c = chunk(1), chunk(2), chunk(3)
    fused = rrf([[a, b, c], [b, c, a]], k=60)
    assert fused[0][0].chunk_id == b.chunk_id  # ranked 2nd and 1st beats 1st and 3rd
    assert len(fused) == 3


def test_parse_citations():
    assert parse_citations("A [1]. B [2, 3]. C [1][4].") == [1, 2, 3, 4]
    assert parse_citations("no cites") == []


def test_abstention_detection():
    assert is_abstention(IDK)
    assert not is_abstention("Use `Depends` [1].")


def test_needs_rewrite():
    assert needs_rewrite("cors?")
    assert needs_rewrite("How do I add CORS? And how do I test it?")
    assert not needs_rewrite("How do I return a custom status code from a path operation")


class FakeLLM:
    model = "fake"

    def __init__(self, text):
        self.text = text

    def complete(self, messages, **kw):
        assert "Sources:" in messages[-1]["content"]
        return LLMResult(self.text, "fake", 100, 20, 0, 5.0)


def test_generate_drops_invalid_citations():
    hits = [Hit(chunk(1), 1.0), Hit(chunk(2), 0.5)]
    gen = generate("q", hits, FakeLLM("Answer one [1]. Answer two [2]. Made up [7]."))
    assert [c.n for c in gen.citations] == [1, 2]
    assert gen.invalid_citations == [7]
    assert not gen.abstained


def test_native_gpt_oss_citations_are_normalized():
    hits = [Hit(chunk(1), 1.0), Hit(chunk(2), 0.5)]
    gen = generate("q", hits, FakeLLM("Since 0.95.0【2】. Also this 【1†L3-L5】."))
    assert gen.answer == "Since 0.95.0[2]. Also this [1]."
    assert [c.n for c in gen.citations] == [1, 2]


def test_generate_without_hits_abstains():
    gen = generate("q", [], FakeLLM("unused"))
    assert gen.abstained and gen.answer == IDK


class FakeEncoders:
    def rerank(self, query, texts):
        # a chunk is relevant only to the sub-query that shares its topic word
        return [5.0 if query.split()[0] in t else -5.0 for t in texts]


def test_multi_part_rerank_keeps_every_part():
    from types import SimpleNamespace

    from librarian.retrieval import Retriever

    cors = [chunk(i) for i in range(1, 7)]
    tests = [chunk(i) for i in range(11, 17)]
    for c in cors:
        c.text = "cors middleware"
    for c in tests:
        c.text = "testing client"
    settings = SimpleNamespace(rerank_candidates=20, top_k=6)
    r = Retriever(settings, store=None, encoders=FakeEncoders())
    per_query = [[(c, 1.0) for c in cors + tests], [(c, 1.0) for c in cors], [(c, 1.0) for c in tests]]
    hits = r._rerank_per_subquery(["cors setup", "testing setup"], per_query, top_k=6)[:6]
    topics = {h.chunk.text for h in hits}
    assert topics == {"cors middleware", "testing client"}
