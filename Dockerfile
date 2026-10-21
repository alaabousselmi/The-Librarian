FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    MODEL_CACHE_DIR=/models \
    DATA_DIR=/app/data \
    PORT=8000

# Non-root user (uid 1000 is also what Hugging Face Spaces runs as)
RUN useradd -m -u 1000 app
WORKDIR /app

COPY pyproject.toml README.md ./
COPY librarian ./librarian
RUN pip install .

# Bake the embedding, BM25 and reranker models into the image: no download at cold start.
RUN mkdir -p /models /app/data && \
    python -c "from librarian.config import Settings; from librarian.embeddings import Encoders; Encoders(Settings()).warmup()" && \
    chown -R app:app /models /app

COPY --chown=app:app eval ./eval
COPY --chown=app:app data/eval ./data/eval

USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s CMD python -c "import urllib.request,os; urllib.request.urlopen(f'http://localhost:{os.environ[\"PORT\"]}/healthz')"
CMD ["sh", "-c", "uvicorn librarian.api.main:app --host 0.0.0.0 --port ${PORT} --workers 1"]
