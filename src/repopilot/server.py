"""FastAPI app: background indexing jobs, SSE Q&A streaming, citation file viewer."""
from __future__ import annotations

import json
import os
import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable, Iterator
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .agent import Agent, AgentResult
from .demo import AnswerCache, load_manifest
from .diff import fetch_pr_diff, parse_diff, parse_pr_url
from .embed import Embedder, FastEmbedder
from .indexing import IndexManager, repo_id_from_url
from .ingest import clone
from .llm import LLM, make_llm
from .review import PRReviewer
from .store import Store
from .toolbox import ToolRunner
from .tools import ToolError, _resolve


class RateLimiter:
    """Tiny in-memory sliding window per (key, bucket). Fine for a single-process demo."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self.clock, self.hits, self.lock = clock, defaultdict(deque), threading.Lock()

    def allow(self, key: str, limit: int, window: float) -> bool:
        now = self.clock()
        with self.lock:
            q = self.hits[key]
            while q and now - q[0] > window:
                q.popleft()
            if len(q) >= limit:
                return False
            q.append(now)
            return True


class DailyCap:
    """A global budget of live model calls per UTC day, so a public demo cannot spend a whole free quota."""

    def __init__(self, limit: int, today: Callable[[], str] = lambda: time.strftime("%Y-%m-%d", time.gmtime())) -> None:
        self.limit, self.today, self.day, self.used, self.lock = limit, today, "", 0, threading.Lock()

    def _roll(self) -> None:
        if (day := self.today()) != self.day:
            self.day, self.used = day, 0

    def allow(self) -> bool:
        with self.lock:
            self._roll()
            if self.used >= self.limit:
                return False
            self.used += 1
            return True

    @property
    def remaining(self) -> int:
        with self.lock:
            self._roll()
            return max(0, self.limit - self.used)


def _flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


class IndexRequest(BaseModel):
    url: str = Field(max_length=200)


class ReviewRequest(BaseModel):
    url: str = Field(max_length=200)


class AskRequest(BaseModel):
    repo: str = Field(max_length=200)
    question: str = Field(min_length=3, max_length=1000)


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def result_to_dict(r: AgentResult) -> dict:
    return r.to_dict()


def create_app(
    workdir: Path | None = None,
    llm_factory: Callable[[], LLM] = make_llm,
    embedder: Embedder | None = None,
    clone_fn: Callable[[str, Path], Path] = clone,
    diff_fn: Callable[[str, str, int], str] = fetch_pr_diff,
    ask_limit: int = 12,
    index_limit: int = 4,
    demo_mode: bool | None = None,
    demo_dir: Path | None = None,
    static_dir: Path | None = None,
    daily_cap: int | None = None,
    max_chunks: int | None = None,
) -> FastAPI:
    workdir = workdir or Path(os.environ.get("REPOPILOT_WORKDIR", ".repopilot"))
    embedder = embedder or FastEmbedder()
    demo_mode = _flag("REPOPILOT_DEMO_MODE") if demo_mode is None else demo_mode
    demo_dir = demo_dir or Path(os.environ.get("REPOPILOT_DEMO_DIR", "demo"))
    if static_dir is None and os.environ.get("REPOPILOT_STATIC_DIR"):
        static_dir = Path(os.environ["REPOPILOT_STATIC_DIR"])
    if daily_cap is None:
        daily_cap = int(os.environ.get("REPOPILOT_DAILY_ASK_CAP", "150"))
    if max_chunks is None and os.environ.get("REPOPILOT_MAX_CHUNKS"):
        max_chunks = int(os.environ["REPOPILOT_MAX_CHUNKS"])
    manager = IndexManager(workdir, embedder, clone_fn, max_chunks)
    limiter = RateLimiter()
    cap = DailyCap(daily_cap)
    manifest = load_manifest(demo_dir / "manifest.json") if (demo_dir / "manifest.json").exists() else []
    cache = AnswerCache.load(demo_dir / "answers.json")
    live_ok: list[bool] = []  # computed once: whether a model is configured at all

    app = FastAPI(title="RepoPilot", docs_url="/api/docs", openapi_url="/api/openapi.json")
    origins = [o for o in os.environ.get("REPOPILOT_CORS", "http://localhost:3000").split(",") if o]
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST"], allow_headers=["*"])

    def repo_dir(rid: str) -> Path:
        try:
            return manager.repo_dir(rid)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e

    def db_path(rid: str) -> Path:
        return manager.db_path(rid)

    def client_ip(req: Request) -> str:
        return (req.headers.get("x-forwarded-for", "").split(",")[0].strip()) or (req.client.host if req.client else "?")

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True}

    @app.get("/api/config")
    def config() -> dict:
        """What this deployment offers: the seeded repos (with their cached example questions) and its limits."""
        if not live_ok:
            try:
                llm_factory()
                live_ok.append(True)
            except RuntimeError:
                live_ok.append(False)
        repos = []
        for r in manifest:
            job = manager.get(r.id)
            if job and job.status == "ready":
                repos.append({"id": r.id, "name": r.name, "description": r.description, "chunks": job.chunks,
                              "examples": cache.examples(r.id)})
        return {"demo": demo_mode, "indexing": not demo_mode, "live_questions": live_ok[0],
                "daily_remaining": cap.remaining, "repos": repos}

    @app.post("/api/repos", status_code=202)
    def index_repo(body: IndexRequest, req: Request) -> dict:
        try:
            rid = repo_id_from_url(body.url)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        existing = manager.get(rid)
        if existing and existing.status != "error":
            return asdict(existing)
        if demo_mode:
            raise HTTPException(
                403, "This demo serves a fixed set of pre-indexed repositories. To index your own, run RepoPilot locally (see the README)."
            )
        if not limiter.allow(f"index:{client_ip(req)}", index_limit, 3600):
            raise HTTPException(429, "indexing rate limit reached; try again later")
        return asdict(manager.start(body.url))

    @app.get("/api/repos/{rid}")
    def repo_status(rid: str) -> dict:
        repo_dir(rid)  # validates id
        job = manager.get(rid)
        if job:
            return asdict(job)
        raise HTTPException(404, "unknown repo")

    @app.get("/api/repos/{rid}/file")
    def read_lines(rid: str, path: str, start: int = Query(1, ge=1), end: int = Query(80, ge=1)) -> dict:
        root = repo_dir(rid)
        try:
            p = _resolve(root, path)
            if not p.is_file():
                raise ToolError("not a file")
            lines = p.read_text(encoding="utf-8").splitlines()
        except (ToolError, UnicodeDecodeError, FileNotFoundError, OSError) as e:
            raise HTTPException(404, f"cannot read file: {e}") from e
        end = min(end, len(lines), start + 400)
        return {"path": path, "start": start, "end": end, "total": len(lines), "lines": lines[start - 1 : end]}

    @app.post("/api/ask")
    def ask(body: AskRequest, req: Request) -> StreamingResponse:
        rid = body.repo
        root, db = repo_dir(rid), db_path(rid)
        if not db.exists():
            raise HTTPException(404, "repo is not indexed yet")
        if entry := cache.get(rid, body.question):  # a real answer from an evaluation run: free and instant
            return StreamingResponse(
                cached_events(entry), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
            )
        if not limiter.allow(f"ask:{client_ip(req)}", ask_limit, 60):
            raise HTTPException(429, "too many questions; slow down")
        try:
            llm = llm_factory()
        except RuntimeError as e:
            raise HTTPException(503, f"LLM not configured: {e}") from e
        if not cap.allow():
            raise HTTPException(429, "The demo's daily limit for live questions is used up. The example questions still work.")
        agent = Agent(llm, Store(db), embedder, root)

        def events() -> Iterator[str]:
            try:
                for ev in agent.stream(body.question):
                    if ev.kind == "answer":
                        yield sse("answer", result_to_dict(ev.data["result"]))
                    else:
                        yield sse(ev.kind, ev.data)
            except RuntimeError as e:  # provider/network failures
                yield sse("error", {"message": str(e)[:300]})

        return StreamingResponse(
            events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
        )

    @app.post("/api/review")
    def review(body: ReviewRequest, req: Request) -> StreamingResponse:
        try:
            owner, name, number = parse_pr_url(body.url)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        rid = f"{owner}--{name}"
        if not limiter.allow(f"ask:{client_ip(req)}", ask_limit, 60):
            raise HTTPException(429, "too many requests; slow down")
        try:
            llm = llm_factory()
        except RuntimeError as e:
            raise HTTPException(503, f"LLM not configured: {e}") from e
        if not cap.allow():
            raise HTTPException(429, "The demo's daily limit for live requests is used up. Try again tomorrow.")
        try:
            pd = parse_diff(diff_fn(owner, name, number))
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        except RuntimeError as e:
            raise HTTPException(502, str(e)) from e
        if not pd.files:
            raise HTTPException(422, "This pull request has no reviewable changes.")
        # Repo context is optional: if the repo is already indexed, the reviewer can look things up.
        tools = ToolRunner(Store(db_path(rid)), embedder, repo_dir(rid)) if db_path(rid).exists() else None
        reviewer = PRReviewer(llm, pd, tools)

        def events() -> Iterator[str]:
            try:
                for ev in reviewer.stream(f"{owner}/{name}#{number}"):
                    if ev.kind == "review":
                        yield sse("review", {**ev.data["result"].to_dict(), "context": tools is not None})
                    else:
                        yield sse(ev.kind, ev.data)
            except RuntimeError as e:
                yield sse("error", {"message": str(e)[:300]})

        return StreamingResponse(
            events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
        )

    # Serve the exported web UI from the same origin as the API: one service, one URL, no CORS. Mounted last so
    # every /api route above wins.
    if static_dir and Path(static_dir).is_dir():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="web")

    return app


def cached_events(entry: dict) -> Iterator[str]:
    """Replay a stored answer in the same event format as a live one, flagged as cached and with its provenance."""
    for ev in entry.get("events", []):
        if ev.get("kind") in ("tool_call", "tool_result"):
            yield sse(ev["kind"], {k: v for k, v in ev.items() if k not in ("kind", "t")})
    yield sse("answer", {**entry["payload"], "cached": True, "source": entry.get("source", {})})


def app_factory() -> FastAPI:  # uvicorn --factory repopilot.server:app_factory
    return create_app()
