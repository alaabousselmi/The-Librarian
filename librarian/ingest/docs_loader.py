"""Load the official FastAPI documentation (English) from a pinned git ref.

The docs are MkDocs markdown with project-specific extensions that a naive loader
would index as noise:
  * `{* ../../docs_src/x.py hl[3] ln[1:10] *}` and `{!../../docs_src/x.py!}` include
    code from `docs_src/` — we inline the real code, since that is what users ask about.
  * `## Heading { #anchor }` gives explicit anchors — we keep them for deep-link citations.
  * `/// tip | Title ... ///` admonitions and `//// tab | ... ////` tabs.
  * `<dfn>`/`<abbr>` tooltips that carry definitions.
  * `::: fastapi.X` mkdocstrings directives (API reference generated from docstrings;
    not resolvable without importing FastAPI — a known gap, see design.md).
"""

from __future__ import annotations

import io
import logging
import re
import tarfile
from pathlib import Path

import httpx

from librarian.models import Document

log = logging.getLogger(__name__)

SITE = "https://fastapi.tiangolo.com/"
DOCS_PREFIX = "docs/en/docs/"
SKIP_DIRS = {"img", "css", "js"}
# Pages with no answerable content, or that are lists of people (personal data).
SKIP_FILES = {"_llm-test.md", "translation-banner.md", "fastapi-people.md", "newsletter.md"}

INCLUDE_STAR = re.compile(r"\{\*\s*(?P<path>\S+)(?P<opts>[^*]*)\*\}")
INCLUDE_BANG = re.compile(r"\{!>?\s*(?P<path>[^!\s]+)\s*!\}")
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*(?:\{\s*#(?P<anchor>[\w\-]+)\s*\})?\s*$")
ADMONITION_OPEN = re.compile(r"^/{3,4}\s*(\w[\w\-]*)\s*(?:\|\s*(.*))?$")
ADMONITION_CLOSE = re.compile(r"^/{3,4}\s*$")
DFN = re.compile(r"<(dfn|abbr)\s+title=(?:\"([^\"]*)\"|'([^']*)')>(.*?)</\1>", re.S)
HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)
HTML_TAG = re.compile(r"</?(?:a|img|span|div|p|br|em|strong|b|i|u|small|sup|sub|details|summary)\b[^>]*>")
LANG_BY_EXT = {".py": "python", ".toml": "toml", ".json": "json", ".sh": "bash", ".js": "javascript",
               ".html": "html", ".txt": "text", ".md": "markdown", ".yml": "yaml", ".yaml": "yaml",
               ".ini": "ini", ".Dockerfile": "dockerfile", ".css": "css"}


def download_repo(repo: str, ref: str, dest: Path) -> Path:
    """Download only docs/en/docs and docs_src of `repo@ref` into dest (cached)."""
    target = dest / f"{repo.replace('/', '__')}@{ref}"
    if (target / DOCS_PREFIX).exists():
        log.info("Using cached FastAPI docs at %s", target)
        return target
    url = f"https://codeload.github.com/{repo}/tar.gz/{ref}"
    log.info("Downloading %s", url)
    with httpx.Client(follow_redirects=True, timeout=120) as client:
        resp = client.get(url)
        resp.raise_for_status()
    with tarfile.open(fileobj=io.BytesIO(resp.content), mode="r:gz") as tar:
        for member in tar.getmembers():
            # strip the "fastapi-<ref>/" top-level folder
            rel = member.name.split("/", 1)[1] if "/" in member.name else ""
            if not member.isfile() or not (rel.startswith(DOCS_PREFIX) or rel.startswith("docs_src/")):
                continue
            out = target / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            extracted = tar.extractfile(member)
            if extracted:
                out.write_bytes(extracted.read())
    return target


def _line_ranges(opts: str) -> list[tuple[int, int]] | None:
    m = re.search(r"ln\[([^\]]+)\]", opts)
    if not m:
        return None
    ranges = []
    for part in m.group(1).split(","):
        a, _, b = part.strip().partition(":")
        start = int(a) if a else 1
        ranges.append((start, int(b) if b else start))
    return ranges


def _read_include(repo_root: Path, raw_path: str, opts: str = "") -> str | None:
    # Paths are written relative to the mkdocs config dir; anchor on "docs_src/" instead.
    idx = raw_path.find("docs_src/")
    if idx < 0:
        return None
    path = repo_root / raw_path[idx:]
    if not path.exists():
        log.debug("Missing include %s", path)
        return None
    lines = path.read_text(encoding="utf-8").splitlines()
    ranges = _line_ranges(opts)
    if ranges:
        picked: list[str] = []
        for start, end in ranges:
            if picked:
                picked.append("# ...")
            picked.extend(lines[start - 1 : end])
        lines = picked
    lang = LANG_BY_EXT.get(path.suffix, "")
    return f"```{lang}\n" + "\n".join(lines).rstrip() + "\n```"


def clean_markdown(text: str, repo_root: Path) -> str:
    """Resolve includes and strip MkDocs syntax, leaving code fences untouched."""
    text = HTML_COMMENT.sub("", text)
    out: list[str] = []
    in_fence = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            out.append(line)
            continue
        if in_fence:
            # includes inside an explicit fence: inline the raw file, the fence is already there
            if m := INCLUDE_BANG.search(stripped) or INCLUDE_STAR.search(stripped):
                code = _read_include(repo_root, m.group("path"), m.groupdict().get("opts") or "")
                if code:
                    out.extend(code.splitlines()[1:-1])
                    continue
            out.append(line)
            continue
        if stripped.startswith(":::"):  # mkdocstrings directive
            continue
        if m := INCLUDE_STAR.search(stripped) or INCLUDE_BANG.search(stripped):
            code = _read_include(repo_root, m.group("path"), m.groupdict().get("opts") or "")
            if code:
                out.append(code)
            continue
        if ADMONITION_CLOSE.match(stripped):
            out.append("")
            continue
        if m := ADMONITION_OPEN.match(stripped):
            kind, title = m.group(1), (m.group(2) or "").strip()
            label = "Tab" if kind == "tab" else kind.capitalize()
            out.append(f"**{label}: {title}**" if title else f"**{label}:**")
            continue
        line = DFN.sub(lambda d: f"{d.group(4)} ({d.group(2) or d.group(3)})", line)
        line = HTML_TAG.sub("", line)
        out.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()


def page_url(rel_path: str) -> str:
    slug = rel_path[: -len(".md")]
    if slug == "index":
        return SITE
    if slug.endswith("/index"):
        slug = slug[: -len("/index")]
    return f"{SITE}{slug}/"


def load_docs(repo: str, ref: str, raw_dir: Path) -> list[Document]:
    root = download_repo(repo, ref, raw_dir)
    docs_dir = root / DOCS_PREFIX
    documents: list[Document] = []
    for path in sorted(docs_dir.rglob("*.md")):
        rel = path.relative_to(docs_dir).as_posix()
        if rel.split("/")[0] in SKIP_DIRS or path.name in SKIP_FILES:
            continue
        text = clean_markdown(path.read_text(encoding="utf-8"), root)
        if len(text) < 200:  # e.g. reference pages that are only `::: fastapi.X`
            log.debug("Skipping near-empty page %s", rel)
            continue
        title = rel
        for line in text.splitlines():
            if m := HEADING.match(line):
                title = m.group(2).strip()
                break
        documents.append(
            Document(
                doc_id=f"docs:{rel[:-3]}",
                source_type="docs",
                title=title,
                url=page_url(rel),
                text=text,
                section=rel.split("/")[0][:-3] if "/" not in rel else rel.split("/")[0],
                author="FastAPI maintainers",
                extra={"path": rel, "ref": ref},
            )
        )
    log.info("Loaded %d docs pages", len(documents))
    return documents
