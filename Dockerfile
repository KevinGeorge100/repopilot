# One image serves the UI and the API from a single origin (see DEPLOY.md).
#
#   stage 1  builds the web app and exports it as static files
#   stage 2  installs the API, bakes in the embedding model, and indexes the demo repos at their pinned commits,
#            so the running container needs no Hugging Face access and does no heavy work for the demo.

FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
# An empty API URL makes the UI call the API on its own origin.
ENV NEXT_PUBLIC_API_URL="" NEXT_TELEMETRY_DISABLED=1
RUN npm run build


FROM python:3.13-slim
RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /usr/local/bin/uv

# Run as an unprivileged user; everything the server writes lives under /app/data.
RUN useradd --create-home --uid 10001 app && mkdir /app && chown app:app /app
USER app
WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:${PATH}" \
    FASTEMBED_CACHE_PATH=/app/.cache/fastembed

# LICENSE is listed in pyproject's license-files, so the project metadata is invalid without it.
COPY --chown=app:app pyproject.toml uv.lock README.md LICENSE ./
COPY --chown=app:app src ./src
RUN uv sync --frozen --no-dev

# Bake the embedding model into the image (about 130 MB), so cold starts never download it.
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5')"

# Clone and index the three demo repos at their pinned commits. This is the slow step (about 2 minutes on 4
# cores) and it happens once, at build time.
COPY --chown=app:app demo ./demo
RUN repopilot seed --workdir /app/data

COPY --from=web --chown=app:app /web/out ./web-out

# Open mode: the seeded repos are ready instantly and visitors can add public repos, capped in size, count and per day.
# Override any of these in the host's environment; GEMINI_API_KEY is the one secret and is never baked in.
ENV REPOPILOT_WORKDIR=/app/data \
    REPOPILOT_STATIC_DIR=/app/web-out \
    REPOPILOT_DEMO_MODE=0 \
    REPOPILOT_MAX_CHUNKS=1500 \
    REPOPILOT_MAX_USER_REPOS=4 \
    PORT=10000
EXPOSE 10000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/api/health', timeout=4)"
CMD ["sh", "-c", "exec repopilot serve --host 0.0.0.0 --port ${PORT}"]
