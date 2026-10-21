from librarian.chunking import chunk_fixed, chunk_markdown, parse_blocks
from librarian.models import Document

CODE = "```python\n" + "\n".join(f"x{i} = {i}  # some code line" for i in range(40)) + "\n```"

DOC_TEXT = f"""# Query Parameters {{ #query-parameters }}

Intro paragraph about query parameters.

## Defaults {{ #defaults }}

Query parameters can have defaults.

{CODE}

More text after the code.

## Optional parameters {{ #optional-parameters }}

Set the default to None.

### Deep detail

A detail.
"""


def make_doc(text=DOC_TEXT):
    return Document(doc_id="docs:tutorial/query-params", source_type="docs", title="Query Parameters",
                    url="https://fastapi.tiangolo.com/tutorial/query-params/", text=text)


def test_parse_blocks_keeps_code_fence_atomic():
    blocks = parse_blocks(DOC_TEXT)
    code = [b for b in blocks if b.kind == "code"]
    assert len(code) == 1
    assert code[0].text.startswith("```python") and code[0].text.endswith("```")
    headings = [b for b in blocks if b.kind == "heading"]
    assert headings[1].anchor == "defaults" and headings[1].title == "Defaults"


def test_markdown_chunks_split_on_sections_with_anchors():
    chunks = chunk_markdown(make_doc(), size=800, overlap=0)
    urls = [c.url for c in chunks]
    assert urls[0].endswith("#query-parameters")
    assert any(u.endswith("#defaults") for u in urls)
    assert any(u.endswith("#optional-parameters") for u in urls)
    defaults = next(c for c in chunks if c.url.endswith("#defaults"))
    assert defaults.heading_path == ["Query Parameters", "Defaults"]
    assert "```python" in defaults.text and defaults.text.count("```") == 2
    assert [c.position for c in chunks] == list(range(len(chunks)))
    assert len({c.chunk_id for c in chunks}) == len(chunks)


def test_markdown_chunks_respect_budget_and_split_big_code():
    chunks = chunk_markdown(make_doc(), size=120, overlap=20)
    for c in chunks:
        assert c.n_tokens <= 120 + 40  # small slack for joiners/fences
        assert c.text.count("```") % 2 == 0, "code fences must stay balanced"


def test_huge_single_line_is_truncated():
    doc = make_doc("# T\n\nIntro text.\n\n```python\nimg = \"" + "QUJD" * 3000 + "\"\n```\n")
    chunks = chunk_markdown(doc, size=400, overlap=60)
    assert max(c.n_tokens for c in chunks) <= 400
    assert "[truncated]" in chunks[-1].text


def test_overlap_never_exceeds_budget():
    text = "# T\n\n" + "\n\n".join(f"Paragraph {i} " + "word " * 70 for i in range(20))
    chunks = chunk_markdown(make_doc(text), size=200, overlap=60)
    assert max(c.n_tokens for c in chunks) <= 200 + 5
    assert len(chunks) > 5


def test_embed_text_has_breadcrumb():
    chunks = chunk_markdown(make_doc(), size=400, overlap=0)
    deep = next(c for c in chunks if "A detail." in c.text)
    assert deep.embed_text.startswith("Query Parameters > Optional parameters > Deep detail")


def test_fixed_chunker_overlaps():
    doc = make_doc("word " * 1000)
    chunks = chunk_fixed(doc, size=200, overlap=50)
    assert len(chunks) >= 6
    assert all(c.n_tokens <= 200 for c in chunks)
