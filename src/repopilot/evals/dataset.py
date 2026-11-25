"""Evaluation dataset: schema validation, pinned checkouts and self-verification of the ground truth."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ..ingest import validate_url

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
NAME_RE = re.compile(r"^[A-Za-z0-9][\w-]{0,39}$")
CATEGORIES = {"fact", "reasoning", "multi-hop", "negative"}


class DatasetError(ValueError):
    """The dataset file is malformed. The message says which question and why."""


@dataclass(frozen=True)
class Gold:
    path: str
    start: int
    end: int
    anchor: str  # text that must appear inside [start, end]; lets `verify` catch drift


@dataclass(frozen=True)
class Question:
    id: str
    repo: str
    category: str
    question: str
    facts: tuple[str, ...]  # regexes; ALL must match the answer (case-insensitive)
    gold: tuple[Gold, ...]  # evidence ranges; a cited range overlapping any of them counts as a hit
    negative: bool  # the right answer is "this is not in the repo"


@dataclass(frozen=True)
class RepoSpec:
    name: str
    url: str
    sha: str


@dataclass
class Dataset:
    version: int
    repos: dict[str, RepoSpec]
    questions: list[Question]


def _fail(qid: str, msg: str) -> DatasetError:
    return DatasetError(f"{qid}: {msg}")


def parse_dataset(raw: dict) -> Dataset:
    repos: dict[str, RepoSpec] = {}
    for name, spec in (raw.get("repos") or {}).items():
        if not NAME_RE.match(name):
            raise DatasetError(f"repo name {name!r} is invalid")
        try:
            validate_url(spec["url"])
        except (ValueError, KeyError) as e:
            raise DatasetError(f"repo {name}: bad url ({e})") from e
        if not SHA_RE.match(str(spec.get("sha", ""))):
            raise DatasetError(f"repo {name}: sha must be 40 lowercase hex characters")
        repos[name] = RepoSpec(name, spec["url"], spec["sha"])
    if not repos:
        raise DatasetError("no repos defined")

    questions: list[Question] = []
    seen: set[str] = set()
    for item in raw.get("questions") or []:
        qid = str(item.get("id", "")).strip()
        if not qid or qid in seen:
            raise DatasetError(f"{qid or '(no id)'}: id missing or duplicated")
        seen.add(qid)
        if item.get("repo") not in repos:
            raise _fail(qid, f"unknown repo {item.get('repo')!r}")
        if item.get("category") not in CATEGORIES:
            raise _fail(qid, f"category must be one of {sorted(CATEGORIES)}")
        text = str(item.get("question", "")).strip()
        if len(text) < 10:
            raise _fail(qid, "question is too short")
        facts = tuple(item.get("facts") or ())
        if not facts:
            raise _fail(qid, "at least one fact regex is required")
        for pattern in facts:
            try:
                re.compile(pattern)
            except re.error as e:
                raise _fail(qid, f"fact regex {pattern!r} does not compile ({e})") from e
        negative = bool(item.get("negative"))
        gold = []
        for g in item.get("gold") or ():
            path = str(g.get("path", ""))
            if not path or path.startswith("/") or ".." in Path(path).parts:
                raise _fail(qid, f"gold path {path!r} must be relative to the repo")
            if not (isinstance(g.get("start"), int) and isinstance(g.get("end"), int) and 1 <= g["start"] <= g["end"]):
                raise _fail(qid, f"gold range for {path} is invalid")
            if not str(g.get("anchor", "")):
                raise _fail(qid, f"gold range for {path} needs an anchor")
            gold.append(Gold(path, g["start"], g["end"], g["anchor"]))
        if not negative and not gold:
            raise _fail(qid, "a positive question needs gold evidence")
        if negative and item.get("category") != "negative":
            raise _fail(qid, "negative questions must use category 'negative'")
        questions.append(Question(qid, item["repo"], item["category"], text, facts, tuple(gold), negative))
    if not questions:
        raise DatasetError("no questions defined")
    return Dataset(int(raw.get("version", 1)), repos, questions)


def load_dataset(path: str | Path) -> Dataset:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise DatasetError(f"cannot read {path}: {e}") from e
    return parse_dataset(raw)


def verify_gold(ds: Dataset, roots: dict[str, Path]) -> list[str]:
    """Check every gold range against the real files. Returns a list of problems (empty means sound)."""
    problems: list[str] = []
    for q in ds.questions:
        root = roots.get(q.repo)
        if root is None:
            problems.append(f"{q.id}: no checkout for repo {q.repo}")
            continue
        for g in q.gold:
            f = (root / g.path).resolve()
            if root.resolve() not in f.parents or not f.is_file():
                problems.append(f"{q.id}: {g.path} does not exist")
                continue
            lines = f.read_text(encoding="utf-8").splitlines()
            if g.end > len(lines):
                problems.append(f"{q.id}: {g.path}:{g.start}-{g.end} is past the end of the file ({len(lines)} lines)")
            elif g.anchor not in "\n".join(lines[g.start - 1 : g.end]):
                problems.append(f"{q.id}: anchor {g.anchor!r} not found in {g.path}:{g.start}-{g.end}")
    return problems


Runner = Callable[..., subprocess.CompletedProcess]


def _git(run: Runner, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def ensure_checkout(spec: RepoSpec, dest: Path, run: Runner = subprocess.run) -> Path:
    """Make `dest` a checkout of exactly `spec.sha`, so questions always see the code they were written for."""
    if not SHA_RE.match(spec.sha):
        raise DatasetError(f"{spec.name}: invalid sha")
    validate_url(spec.url)
    if (dest / ".git").exists():
        try:
            if _git(run, "rev-parse", "HEAD", cwd=dest).stdout.strip() == spec.sha:
                return dest
        except subprocess.CalledProcessError:
            pass
        shutil.rmtree(dest)  # a stale or damaged checkout owned by the eval workdir
    dest.mkdir(parents=True, exist_ok=True)
    _git(run, "init", "-q", str(dest))
    _git(run, "remote", "add", "origin", spec.url, cwd=dest)
    _git(run, "fetch", "-q", "--depth", "1", "--", "origin", spec.sha, cwd=dest)
    _git(run, "checkout", "-q", "--detach", "FETCH_HEAD", cwd=dest)
    return dest
