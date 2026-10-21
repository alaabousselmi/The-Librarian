"""Command line: `librarian build` (ingest + index), `librarian ask`, `librarian serve`."""

from __future__ import annotations

import json
import logging
from collections import Counter

import typer

from librarian.config import get_settings

app = typer.Typer(help="The Librarian — RAG over the FastAPI docs, Discussions and issues.",
                  no_args_is_help=True)


@app.callback()
def main(verbose: bool = typer.Option(False, "--verbose", "-v")):
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)


@app.command()
def ingest(docs: bool = True, github: bool = True):
    """Download the corpus and write data/processed/documents.jsonl."""
    from librarian.ingest import ingest as run_ingest

    documents = run_ingest(get_settings(), docs=docs, github=github)
    typer.echo(f"{len(documents)} documents: {dict(Counter(d.source_type for d in documents))}")


@app.command()
def index(
    strategy: str = typer.Option(None, help="markdown | fixed (default from CHUNK_STRATEGY)"),
    size: int = typer.Option(None, help="chunk size in tokens"),
    overlap: int = typer.Option(None, help="chunk overlap in tokens"),
    collection: str = typer.Option(None, help="target collection (default COLLECTION)"),
):
    """Chunk documents, embed them and (re)build a Qdrant collection."""
    from librarian.chunking import chunk_documents
    from librarian.embeddings import Encoders
    from librarian.models import load_documents, write_jsonl
    from librarian.store import Store

    s = get_settings()
    strategy, size, overlap = strategy or s.chunk_strategy, size or s.chunk_size, overlap or s.chunk_overlap
    docs = load_documents(s.processed_dir / "documents.jsonl")
    chunks = chunk_documents(docs, strategy, size, overlap)
    name = collection or s.collection
    write_jsonl(s.processed_dir / f"chunks_{name}.jsonl", chunks)
    tokens = [c.n_tokens for c in chunks]
    typer.echo(f"{len(docs)} docs -> {len(chunks)} chunks ({strategy}, size={size}, overlap={overlap}); "
               f"mean {sum(tokens) / len(tokens):.0f} tokens, max {max(tokens)}")
    store = Store(s, Encoders(s), collection=name)
    store.recreate()
    store.upsert(chunks)
    n = store.count()
    typer.echo(f"Collection '{name}' has {n} points")
    if n != len(chunks):
        raise typer.Exit(f"Index has {n} points but {len(chunks)} chunks were written")


@app.command()
def build(github: bool = True):
    """One-shot setup: ingest the corpus, then build the default index."""
    ingest(docs=True, github=github)
    index(strategy=None, size=None, overlap=None, collection=None)


@app.command()
def ask(question: str, mode: str = None, no_rerank: bool = False, show_sources: bool = True):
    """Ask a question from the terminal."""
    from librarian.pipeline import AskOptions, Pipeline

    result = Pipeline(get_settings()).ask(
        question, options=AskOptions(mode=mode, rerank=False if no_rerank else None))
    typer.echo(result.answer)
    if show_sources:
        typer.echo("\nSources:")
        for c in result.citations:
            typer.echo(f"  [{c.n}] {c.title} — {c.url}")
    typer.echo("\n" + json.dumps({"queries": result.queries, "timings_ms": result.timings_ms,
                                  "usage": result.usage, "abstain_reason": result.abstain_reason}))


@app.command()
def serve(host: str = "0.0.0.0", port: int = 8000, reload: bool = False):
    """Run the web service."""
    import uvicorn

    uvicorn.run("librarian.api.main:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    app()
