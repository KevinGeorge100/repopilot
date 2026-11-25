"""FastAPI app: background indexing jobs, SSE Q&A streaming, citation file viewer."""
from __future__ import annotations

import json
import os
import re
import shutil
import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .agent import Agent, AgentResult
from .diff import fetch_pr_diff, parse_diff, parse_pr_url
from .embed import Embedder, FastEmbedder
from .ingest import clone, validate_url
from .llm import LLM, make_llm
from .pipeline import build_index
from .review import PRReviewer
from .store import Store
from .toolbox import ToolRunner
from .tools import ToolError, _resolve

REPO_ID = re.compile(r"^[\w.-]+--[\w.-]+$")


@dataclass
class Job:
    id: str
    url: str
    status: str = "queued"  # queued|cloning|chunking|embedding|ready|error
    done: int = 0
    total: int = 0
    chunks: int = 0
    truncated: bool = False
    error: str | None = None


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


class IndexRequest(BaseModel):
    url: str = Field(max_length=200)


class ReviewRequest(BaseModel):
    url: str = Field(max_length=200)


class AskRequest(BaseModel):
    repo: str = Field(max_length=200)
    question: str = Field(min_length=3, max_length=1000)


def repo_id_from_url(url: str) -> str:
    owner, name = validate_url(url).rstrip("/").removesuffix(".git").split("/")[-2:]
    return f"{owner}--{name}"


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def result_to_dict(r: AgentResult) -> dict:
    c = r.citations
    return {
        "answer": r.answer,
        "stopped": r.stopped,
        "steps": r.steps,
        "usage": asdict(r.usage),
        "citations": {
            "valid": [{"path": x.path, "start": x.start, "end": x.end} for x in c.cited],
            "invalid": [{"citation": a, "reason": b} for a, b in c.invalid],
            "ungrounded": c.ungrounded,
            "validity": c.validity,
            "ok": c.ok,
        },
    }


def create_app(
    workdir: Path | None = None,
    llm_factory: Callable[[], LLM] = make_llm,
    embedder: Embedder | None = None,
    clone_fn: Callable[[str, Path], Path] = clone,
    diff_fn: Callable[[str, str, int], str] = fetch_pr_diff,
    ask_limit: int = 12,
    index_limit: int = 4,
) -> FastAPI:
    workdir = workdir or Path(os.environ.get("REPOPILOT_WORKDIR", ".repopilot"))
    embedder = embedder or FastEmbedder()
    jobs: dict[str, Job] = {}
    lock = threading.Lock()
    pool = ThreadPoolExecutor(max_workers=1)  # one index at a time: CPU-bound
    limiter = RateLimiter()

    app = FastAPI(title="RepoPilot", docs_url="/api/docs", openapi_url="/api/openapi.json")
    origins = [o for o in os.environ.get("REPOPILOT_CORS", "http://localhost:3000").split(",") if o]
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST"], allow_headers=["*"])

    def repo_dir(rid: str) -> Path:
        if not REPO_ID.match(rid):
            raise HTTPException(400, "invalid repo id")
        return workdir / "repos" / rid

    def db_path(rid: str) -> Path:
        return workdir / "index" / f"{rid}.db"

    def client_ip(req: Request) -> str:
        return (req.headers.get("x-forwarded-for", "").split(",")[0].strip()) or (req.client.host if req.client else "?")

    def run_index(job: Job) -> None:
        def progress(phase: str, done: int, total: int) -> None:
            job.status, job.done, job.total = phase, done, total

        try:
            job.status = "cloning"
            dest = repo_dir(job.id)
            dest.parent.mkdir(parents=True, exist_ok=True)
            clone_fn(job.url, dest)
            summary = build_index(dest, db_path(job.id), embedder, progress)
            job.chunks, job.truncated, job.status = summary.chunks, summary.truncated, "ready"
        except Exception as e:  # noqa: BLE001 - surface any failure to the UI, never crash the worker
            job.status, job.error = "error", f"{type(e).__name__}: {str(e)[:200]}"
            shutil.rmtree(repo_dir(job.id), ignore_errors=True)

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True}

    @app.post("/api/repos", status_code=202)
    def index_repo(body: IndexRequest, req: Request) -> dict:
        try:
            rid = repo_id_from_url(body.url)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        with lock:
            existing = jobs.get(rid)
            if existing and existing.status not in ("error",):
                return asdict(existing)
            if db_path(rid).exists() and not existing:
                jobs[rid] = Job(rid, body.url, "ready", chunks=Store(db_path(rid)).count())
                return asdict(jobs[rid])
            if not limiter.allow(f"index:{client_ip(req)}", index_limit, 3600):
                raise HTTPException(429, "indexing rate limit reached; try again later")
            job = jobs[rid] = Job(rid, body.url)
        pool.submit(run_index, job)
        return asdict(job)

    @app.get("/api/repos/{rid}")
    def repo_status(rid: str) -> dict:
        repo_dir(rid)  # validates id
        job = jobs.get(rid)
        if job:
            return asdict(job)
        if db_path(rid).exists():
            return asdict(Job(rid, "", "ready", chunks=Store(db_path(rid)).count()))
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
        if not limiter.allow(f"ask:{client_ip(req)}", ask_limit, 60):
            raise HTTPException(429, "too many questions; slow down")
        try:
            llm = llm_factory()
        except RuntimeError as e:
            raise HTTPException(503, f"LLM not configured: {e}") from e
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

    return app


def app_factory() -> FastAPI:  # uvicorn --factory repopilot.server:app_factory
    return create_app()
