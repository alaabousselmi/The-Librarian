from librarian.ingest.docs_loader import clean_markdown, page_url
from librarian.ingest.github_loader import discussion_to_document


def test_include_and_mkdocs_syntax(tmp_path):
    src = tmp_path / "docs_src" / "query_params"
    src.mkdir(parents=True)
    (src / "tutorial001.py").write_text("line1\nline2\nline3\nline4\n", encoding="utf-8")
    md = """# Title { #title }

{* ../../docs_src/query_params/tutorial001.py hl[2] *}

{* ../../docs_src/query_params/tutorial001.py ln[2:3] *}

/// tip | Good to know

Use <dfn title="a thing">jargon</dfn> carefully, <abbr title='single "quoted"'>SQ</abbr>.

///

::: fastapi.FastAPI
"""
    out = clean_markdown(md, tmp_path)
    assert "```python\nline1\nline2\nline3\nline4\n```" in out
    assert "```python\nline2\nline3\n```" in out
    assert "**Tip: Good to know**" in out
    assert "jargon (a thing)" in out
    assert 'SQ (single "quoted")' in out
    assert ":::" not in out and "///" not in out


def test_include_inside_existing_fence(tmp_path):
    (tmp_path / "docs_src").mkdir()
    (tmp_path / "docs_src" / "a.js").write_text("const a = 1;", encoding="utf-8")
    out = clean_markdown("```JavaScript\n{!> ../../docs_src/a.js!}\n```", tmp_path)
    assert out == "```JavaScript\nconst a = 1;\n```"


def test_page_url():
    assert page_url("index.md") == "https://fastapi.tiangolo.com/"
    assert page_url("tutorial/index.md") == "https://fastapi.tiangolo.com/tutorial/"
    assert page_url("tutorial/query-params.md") == "https://fastapi.tiangolo.com/tutorial/query-params/"


def test_discussion_document_has_no_usernames():
    d = {
        "number": 42, "title": "How to X?", "url": "https://github.com/fastapi/fastapi/discussions/42",
        "body": "I want X", "createdAt": "2024-01-01T00:00:00Z", "updatedAt": "2024-01-02T00:00:00Z",
        "authorAssociation": "NONE", "upvoteCount": 3, "isAnswered": True,
        "category": {"name": "Questions"}, "labels": {"nodes": [{"name": "question"}]},
        "answer": {"body": "Do Y", "authorAssociation": "MEMBER", "upvoteCount": 5},
        "comments": {"nodes": [{"body": "Thanks", "authorAssociation": "NONE", "upvoteCount": 0, "isAnswer": False}]},
    }
    doc = discussion_to_document(d)
    assert doc.doc_id == "discussion:42" and doc.section == "Questions"
    assert "Accepted answer (by a maintainer)" in doc.text and "Do Y" in doc.text
    assert doc.author == "community"
