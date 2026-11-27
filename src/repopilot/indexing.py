"""Background indexing jobs, shared by the HTTP API and the MCP server."""
from __future__ import annotations

import re
import shutil
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from .embed import Embedder
from .ingest import clone, validate_url
from .pipeline import build_index
from .store import Store

REPO_ID = re.compile(r"^\w[\w-]*--(?!\.{1,2}$)[\w.-]+$")


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


def repo_id_from_url(url: str) -> str:
    owner, name = validate_url(url).rstrip("/").removesuffix(".git").split("/")[-2:]
    return f"{owner}--{name}"


class IndexManager:
    """Owns clone and index locations plus the job table. One index runs at a time (CPU-bound)."""

    def __init__(
        self,
        workdir: Path,
        embedder: Embedder,
        clone_fn: Callable[[str, Path], Path] = clone,
        max_chunks: int | None = None,
        protected: frozenset[str] = frozenset(),
        max_user_repos: int = 6,
    ) -> None:
        self.workdir, self.embedder, self.clone_fn = workdir, embedder, clone_fn
        self.max_chunks = max_chunks  # None means the pipeline default; a small host can lower it
        self.protected, self.max_user_repos = protected, max_user_repos  # protected ids are never evicted
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=1)

    def repo_dir(self, rid: str) -> Path:
        if not REPO_ID.match(rid):
            raise ValueError("invalid repo id")
        return self.workdir / "repos" / rid

    def db_path(self, rid: str) -> Path:
        if not REPO_ID.match(rid):
            raise ValueError("invalid repo id")
        return self.workdir / "index" / f"{rid}.db"

    def get(self, rid: str) -> Job | None:
        """The live job, or a 'ready' job rebuilt from an index that survived a restart."""
        self.repo_dir(rid)  # validates the id
        job = self._jobs.get(rid)
        if job or not self.db_path(rid).exists():
            return job
        store = Store(self.db_path(rid))
        try:
            return Job(rid, "", "ready", chunks=store.count())
        finally:
            store.db.close()

    def start(self, url: str) -> Job:
        """Idempotent: returns the existing job unless the last attempt failed. Raises ValueError for bad URLs."""
        rid = repo_id_from_url(url)
        with self._lock:
            existing = self.get(rid)
            if existing and existing.status != "error":
                self._jobs.setdefault(rid, existing)
                return existing
            job = self._jobs[rid] = Job(rid, url)
        self._pool.submit(self._run, job)
        return job

    def _run(self, job: Job) -> None:
        def progress(phase: str, done: int, total: int) -> None:
            job.status, job.done, job.total = phase, done, total

        try:
            job.status = "cloning"
            dest = self.repo_dir(job.id)
            dest.parent.mkdir(parents=True, exist_ok=True)
            self.clone_fn(job.url, dest)
            extra = {"max_chunks": self.max_chunks} if self.max_chunks else {}
            summary = build_index(dest, self.db_path(job.id), self.embedder, progress, **extra)
            job.chunks, job.truncated, job.status = summary.chunks, summary.truncated, "ready"
            self.prune()
        except Exception as e:  # noqa: BLE001 - surface any failure to the caller, never crash the worker
            # Our own ValueErrors are written for the user; anything else keeps its type name for debugging.
            job.status, job.error = "error", str(e)[:200] if isinstance(e, ValueError) else f"{type(e).__name__}: {str(e)[:200]}"
            shutil.rmtree(self.repo_dir(job.id), ignore_errors=True)

    def touch(self, rid: str) -> None:
        """Mark a repo as recently used, so eviction removes the least recently used one."""
        try:
            self.db_path(rid).touch()
        except (OSError, ValueError):
            pass

    def prune(self) -> list[str]:
        """Keep at most max_user_repos non-protected repos on disk (a hosted instance has little of it)."""
        idx = self.workdir / "index"
        if not idx.exists():
            return []
        mine = [p for p in idx.glob("*.db") if p.stem not in self.protected]
        mine.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        gone = []
        for p in mine[self.max_user_repos:]:
            rid = p.stem
            job = self._jobs.get(rid)
            if job and job.status not in ("ready", "error"):
                continue
            p.unlink(missing_ok=True)
            shutil.rmtree(self.workdir / "repos" / rid, ignore_errors=True)
            self._jobs.pop(rid, None)
            gone.append(rid)
        return gone
