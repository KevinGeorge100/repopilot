"""Showcase support: a manifest of demo repos, build-time seeding of them, and cached example answers.

A public demo must work when the free model quota is spent, so the examples are answers that really came out of an
evaluation run. They are served instantly and labelled as cached; anything typed in is answered live.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .embed import Embedder
from .evals.dataset import Dataset, RepoSpec, Runner, ensure_checkout
from .indexing import repo_id_from_url
from .pipeline import build_index

CATEGORY_ORDER = ("fact", "reasoning", "multi-hop", "negative")


@dataclass(frozen=True)
class DemoRepo:
    id: str
    name: str  # owner/name
    url: str
    sha: str
    description: str


def load_manifest(path: Path) -> list[DemoRepo]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    repos: list[DemoRepo] = []
    for item in raw.get("repos", []):
        rid = repo_id_from_url(item["url"])  # validates the URL
        if not re.fullmatch(r"[0-9a-f]{40}", item.get("sha", "")):
            raise ValueError(f"{rid}: sha must be 40 hex characters")
        repos.append(DemoRepo(rid, rid.replace("--", "/", 1), item["url"], item["sha"], item.get("description", "")))
    return repos


def normalize_question(q: str) -> str:
    return " ".join(re.findall(r"[a-z0-9_]+", q.lower()))


class AnswerCache:
    """Real answers from an evaluation run, keyed by repo and normalised question."""

    def __init__(self, entries: list[dict[str, Any]] | None = None) -> None:
        self._by_key: dict[tuple[str, str], dict[str, Any]] = {}
        self._order: dict[str, list[str]] = {}
        for e in entries or []:
            self._by_key[(e["repo"], normalize_question(e["question"]))] = e
            self._order.setdefault(e["repo"], []).append(e["question"])

    @classmethod
    def load(cls, path: Path) -> AnswerCache:
        if not path.exists():
            return cls()
        return cls(json.loads(path.read_text(encoding="utf-8")).get("answers", []))

    def get(self, repo: str, question: str) -> dict[str, Any] | None:
        return self._by_key.get((repo, normalize_question(question)))

    def examples(self, repo: str) -> list[str]:
        return list(self._order.get(repo, []))

    def __len__(self) -> int:
        return len(self._by_key)


def seed_demo(
    repos: list[DemoRepo],
    workdir: Path,
    embedder: Embedder,
    log: Callable[[str], None] = print,
    force: bool = False,
    strip_git: bool = True,
    run: Runner = subprocess.run,
    max_chunks: int | None = None,
) -> dict[str, dict[str, Any]]:
    """Clone each demo repo at its pinned commit and index it, so the served image needs no network or CPU for it."""
    out: dict[str, dict[str, Any]] = {}
    for r in repos:
        dest = workdir / "repos" / r.id
        db = workdir / "index" / f"{r.id}.db"
        if db.exists() and dest.exists() and not force:
            log(f"  {r.name}: already seeded")
            continue
        ensure_checkout(RepoSpec(r.id, r.url, r.sha), dest, run)
        t0 = time.monotonic()
        kwargs = {"max_chunks": max_chunks} if max_chunks else {}
        summary = build_index(dest, db, embedder, **kwargs)
        if strip_git:
            shutil.rmtree(dest / ".git", ignore_errors=True)  # only the checkout we just made in the build dir
        out[r.id] = {"chunks": summary.chunks, "seconds": round(time.monotonic() - t0, 1)}
        log(f"  {r.name}: {summary.chunks} chunks in {out[r.id]['seconds']}s")
    return out


def export_answers(
    ds: Dataset,
    traces: list[dict[str, Any]],
    manifest: list[DemoRepo],
    per_repo: int = 6,
    source: dict[str, Any] | None = None,
    exclude: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Pick real, passing answers from an evaluation run to ship as cached examples.

    `exclude` drops specific questions by id, for example an answer with a wording slip a reviewer caught.
    Only answers that passed scoring with a finished run and valid citations are used, spread over question types,
    with at most one "not in this repo" answer per repo. Nothing is edited: payload and events are copied verbatim.
    """
    by_url = {r.url: r.id for r in manifest}
    ids = {name: by_url[spec.url] for name, spec in ds.repos.items() if spec.url in by_url}
    questions = {q.id: q for q in ds.questions}
    chosen: list[dict[str, Any]] = []
    for name, rid in ids.items():
        pool = [
            t for t in traces
            if t["repo"] == name and t["score"]["passed"] and not t.get("error")
            and t["payload"]["stopped"] == "done" and t["payload"]["answer"].strip()
            and t["payload"]["citations"]["ok"] is not False and t["id"] in questions
            and t["id"] not in (exclude or set())
        ]
        by_cat: dict[str, list[dict[str, Any]]] = {c: [] for c in CATEGORY_ORDER}
        for t in sorted(pool, key=lambda t: t["id"]):
            by_cat.setdefault(t["category"], []).append(t)
        picked: list[dict[str, Any]] = []
        negatives = 0
        while len(picked) < per_repo and any(by_cat.values()):
            for cat in CATEGORY_ORDER:
                if not by_cat.get(cat) or len(picked) >= per_repo:
                    continue
                if cat == "negative" and negatives >= 1:
                    by_cat[cat] = []
                    continue
                picked.append(by_cat[cat].pop(0))
                negatives += cat == "negative"
        for t in picked:
            chosen.append({
                "repo": rid, "question": questions[t["id"]].question, "events": t["events"], "payload": t["payload"],
                "source": source or {},
            })
    return chosen
