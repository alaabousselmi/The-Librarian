"""Load FastAPI GitHub Discussions (GraphQL) and closed issues (REST).

FastAPI moved almost all user Q&A from issues to Discussions, so discussions are
the main "community" source; issues add bug/behaviour reports.

Privacy: we never store GitHub logins. Authors are reduced to their association
with the repo (MEMBER / CONTRIBUTOR / NONE ...), which is what matters for trust
("is this answer from a maintainer?").
Raw API pages are cached under data/raw/github so re-ingests are cheap.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import httpx

from librarian.models import Document

log = logging.getLogger(__name__)

API = "https://api.github.com"
MAX_COMMENTS = 8

DISCUSSIONS_QUERY = """
query($owner: String!, $name: String!, $after: String) {
  repository(owner: $owner, name: $name) {
    discussions(first: 50, after: $after, orderBy: {field: CREATED_AT, direction: DESC}) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number title url body createdAt updatedAt upvoteCount authorAssociation
        category { name }
        labels(first: 10) { nodes { name } }
        isAnswered
        answer { body authorAssociation upvoteCount }
        comments(first: 8) { nodes { body authorAssociation upvoteCount isAnswer } }
      }
    }
  }
}
"""


def _role(assoc: str | None) -> str:
    return {"OWNER": "maintainer", "MEMBER": "maintainer", "COLLABORATOR": "maintainer",
            "CONTRIBUTOR": "contributor"}.get(assoc or "", "community")


class GitHub:
    def __init__(self, token: str, cache_dir: Path):
        if not token:
            raise ValueError("GITHUB_TOKEN is required to load discussions/issues (see .env.example)")
        self.client = httpx.Client(
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
            timeout=60,
        )
        self.cache_dir = cache_dir
        cache_dir.mkdir(parents=True, exist_ok=True)

    def _request(self, method: str, url: str, **kw) -> httpx.Response:
        for attempt in range(6):
            resp = self.client.request(method, url, **kw)
            remaining = resp.headers.get("x-ratelimit-remaining")
            if resp.status_code in (403, 429) and remaining == "0":
                wait = max(int(resp.headers.get("x-ratelimit-reset", time.time() + 60)) - time.time(), 1)
                log.warning("GitHub rate limit hit, sleeping %.0fs", wait)
                time.sleep(min(wait + 1, 900))
                continue
            if resp.status_code >= 500 or resp.status_code in (403, 429):
                time.sleep(2**attempt)
                continue
            resp.raise_for_status()
            return resp
        resp.raise_for_status()
        return resp

    def _cached(self, key: str, fetch) -> dict | list:
        path = self.cache_dir / f"{key}.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        data = fetch()
        path.write_text(json.dumps(data), encoding="utf-8")
        return data

    def discussions(self, repo: str, limit: int) -> list[dict]:
        owner, name = repo.split("/")
        nodes: list[dict] = []
        after, page = None, 0
        while len(nodes) < limit:
            def fetch(after=after):
                resp = self._request("POST", f"{API}/graphql", json={
                    "query": DISCUSSIONS_QUERY,
                    "variables": {"owner": owner, "name": name, "after": after},
                })
                body = resp.json()
                if "errors" in body:
                    raise RuntimeError(body["errors"])
                return body["data"]["repository"]["discussions"]
            data = self._cached(f"discussions_p{page:04d}", fetch)
            nodes.extend(data["nodes"])
            page += 1
            log.info("Fetched %d discussions", len(nodes))
            if not data["pageInfo"]["hasNextPage"]:
                break
            after = data["pageInfo"]["endCursor"]
        return nodes[:limit]

    def closed_issues(self, repo: str, limit: int) -> list[dict]:
        issues: list[dict] = []
        page = 1
        while len(issues) < limit:
            batch = self._cached(f"issues_p{page:04d}", lambda page=page: self._request(
                "GET", f"{API}/repos/{repo}/issues",
                params={"state": "closed", "per_page": 100, "page": page, "sort": "comments"},
            ).json())
            if not batch:
                break
            # The issues endpoint also returns PRs; keep real issues that got replies.
            issues.extend(i for i in batch if "pull_request" not in i and i.get("comments", 0) > 0)
            page += 1
        issues = issues[:limit]
        for issue in issues:
            issue["_comments"] = self._cached(f"issue_{issue['number']}_comments", lambda n=issue["number"]: self._request(
                "GET", f"{API}/repos/{repo}/issues/{n}/comments", params={"per_page": MAX_COMMENTS},
            ).json())
        return issues


def discussion_to_document(d: dict) -> Document:
    parts = [f"# {d['title']}", "", "## Question", "", (d.get("body") or "").strip()]
    if d.get("answer"):
        a = d["answer"]
        parts += ["", f"## Accepted answer (by a {_role(a['authorAssociation'])})", "", a["body"].strip()]
    others = [c for c in d["comments"]["nodes"] if not c.get("isAnswer")]
    others.sort(key=lambda c: c.get("upvoteCount", 0), reverse=True)
    for c in others[:4]:
        parts += ["", f"## Reply (by a {_role(c['authorAssociation'])})", "", c["body"].strip()]
    labels = [n["name"] for n in d["labels"]["nodes"]]
    return Document(
        doc_id=f"discussion:{d['number']}",
        source_type="discussion",
        title=d["title"],
        url=d["url"],
        text="\n".join(parts).strip(),
        section=d["category"]["name"] if d.get("category") else None,
        created_at=d["createdAt"],
        updated_at=d["updatedAt"],
        author=_role(d.get("authorAssociation")),
        extra={"answered": d.get("isAnswered", False), "upvotes": d.get("upvoteCount", 0),
               "labels": labels},
    )


def issue_to_document(i: dict) -> Document:
    parts = [f"# {i['title']}", "", "## Issue", "", (i.get("body") or "").strip()]
    for c in i.get("_comments", [])[:MAX_COMMENTS]:
        parts += ["", f"## Comment (by a {_role(c.get('author_association'))})", "", (c.get("body") or "").strip()]
    labels = [lbl["name"] for lbl in i.get("labels", [])]
    return Document(
        doc_id=f"issue:{i['number']}",
        source_type="issue",
        title=i["title"],
        url=i["html_url"],
        text="\n".join(parts).strip(),
        section=labels[0] if labels else None,
        created_at=i["created_at"],
        updated_at=i.get("closed_at") or i["updated_at"],
        author=_role(i.get("author_association")),
        extra={"labels": labels, "state_reason": i.get("state_reason")},
    )


def load_github(repo: str, token: str, raw_dir: Path, max_discussions: int, max_issues: int,
                only_answered: bool = True) -> list[Document]:
    gh = GitHub(token, raw_dir / "github")
    discussions = gh.discussions(repo, max_discussions)
    if only_answered:
        discussions = [d for d in discussions if d.get("isAnswered")]
    docs = [discussion_to_document(d) for d in discussions]
    if max_issues:
        docs += [issue_to_document(i) for i in gh.closed_issues(repo, max_issues)]
    log.info("Loaded %d GitHub documents", len(docs))
    return docs
