# Backend image (API + indexer). The frontend deploys separately (e.g. Vercel).
FROM python:3.13-slim
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev
# Bake the embedding model into the image so the container needs no Hugging Face access at runtime.
RUN uv run python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5')"
ENV REPOPILOT_WORKDIR=/data PORT=8000
VOLUME /data
EXPOSE 8000
CMD ["sh", "-c", "uv run repopilot serve --host 0.0.0.0 --port ${PORT}"]
