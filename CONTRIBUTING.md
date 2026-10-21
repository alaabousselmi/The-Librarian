# Contributing

## Workflow

1. Pick a task from [`docs/PLAN.md`](docs/PLAN.md) (or a GitHub issue) and assign it to yourself.
2. Branch from `main`: `feat/<short-name>`, `fix/<short-name>`, `eval/<short-name>`.
3. Keep PRs small; CI (ruff + pytest + docker build) must be green; one teammate reviews.
4. Squash-merge. Update the task status in `docs/PLAN.md` in the same PR.

## Setup

```bash
python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env                            # add your own keys
librarian build                                 # ingest + index (embedded Qdrant)
pytest -q && ruff check librarian tests eval
```

## Rules

* **Never commit secrets** (`.env`, tokens) or raw corpus data (`data/raw`, `data/processed`).
* Any change that could affect quality (chunking, prompts, retrieval params, models) must come with
  eval numbers in the PR description: `python eval/ablation.py` and/or `python eval/generation_eval.py`.
* New eval questions go through review: a second person checks the answer and the gold passage
  against the source and sets `"verified": true`.
* Log problems in [`docs/postmortem.md`](docs/postmortem.md) when they happen, not at the end.
* You must be able to explain every line you merge.
