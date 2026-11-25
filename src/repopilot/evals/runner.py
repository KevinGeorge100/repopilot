"""Run the agent over the dataset and record one trace per question (resumable, rate-limit aware)."""
from __future__ import annotations

import json
import subprocess
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ..agent import Agent
from ..embed import Embedder
from ..llm import LLM
from ..pipeline import build_index
from ..store import EMBED_CHARS, INDEX_VERSION, Store
from ..toolbox import MAX_TOOL_RESULT_CHARS, ToolRunner
from .dataset import Dataset, Runner, ensure_checkout
from .metrics import score_answer


@dataclass(frozen=True)
class RepoHandle:
    root: Path
    db: Path


@dataclass
class RunConfig:
    label: str
    provider: str | None = None
    model: str | None = None
    search_k: int = 8
    max_result_chars: int = MAX_TOOL_RESULT_CHARS
    max_steps: int = 8
    token_budget: int = 150_000  # per question
    retries: int = 1  # extra attempts when the provider fails (not when the answer is wrong)
    retry_wait_s: float = 5.0  # first backoff after a provider failure; doubles in effect per attempt
    abort_after: int = 5  # stop the run after this many questions in a row fail on the provider (outage)
    min_interval_s: float = 0.0  # pause between questions, for free-tier rate limits
    token_cap: int | None = None  # stop the whole run once this many tokens were used


def prepare_repos(
    ds: Dataset,
    workdir: Path,
    embedder: Embedder,
    log: Callable[[str], None] = print,
    force: bool = False,
    run: Runner = subprocess.run,
) -> tuple[dict[str, RepoHandle], dict[str, dict[str, Any]]]:
    """Check out each repo at its pinned commit and index it, reusing an index built for the same commit."""
    handles: dict[str, RepoHandle] = {}
    stats: dict[str, dict[str, Any]] = {}
    for name, spec in ds.repos.items():
        root = ensure_checkout(spec, workdir / "repos" / name, run)
        db = workdir / "index" / f"{name}.db"
        marker = workdir / "index" / f"{name}.json"
        if not force and db.exists() and marker.exists():
            info = json.loads(marker.read_text())
            if info.get("sha") == spec.sha and info.get("index_version") == INDEX_VERSION:
                log(f"  {name}: reusing index ({info['chunks']} chunks, built in {info['index_seconds']:.0f}s)")
                handles[name], stats[name] = RepoHandle(root, db), info
                continue
        log(f"  {name}: indexing at {spec.sha[:8]} ...")
        t0 = time.monotonic()
        summary = build_index(root, db, embedder)
        info = {
            "sha": spec.sha,
            "index_version": INDEX_VERSION,
            "embed_chars": EMBED_CHARS,
            "chunks": summary.chunks,
            "chunks_found": summary.total_chunks_found,
            "truncated": summary.truncated,
            "index_seconds": round(time.monotonic() - t0, 1),
        }
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(json.dumps(info))
        log(f"  {name}: {info['chunks']} chunks in {info['index_seconds']}s")
        handles[name], stats[name] = RepoHandle(root, db), info
    return handles, stats


def read_traces(path: Path) -> list[dict[str, Any]]:
    """Load traces; if an id appears more than once (a retried error), the last line wins."""
    if not path.exists():
        return []
    latest: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            t = json.loads(line)
            latest[t["id"]] = t
    return list(latest.values())


def run_eval(
    ds: Dataset,
    handles: dict[str, RepoHandle],
    embedder: Embedder,
    llm_factory: Callable[[], LLM],
    config: RunConfig,
    out_dir: Path,
    *,
    index_stats: dict[str, dict[str, Any]] | None = None,
    resume: bool = True,
    only: set[str] | None = None,
    limit: int | None = None,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
    log: Callable[[str], None] = print,
) -> list[dict[str, Any]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    trace_path = out_dir / "traces.jsonl"
    (out_dir / "config.json").write_text(
        json.dumps({"config": asdict(config), "dataset_version": ds.version, "index_stats": index_stats or {},
                    "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, indent=1)
    )
    done = {t["id"]: t for t in read_traces(trace_path) if not t.get("error")} if resume else {}
    if not resume:
        trace_path.write_text("")

    todo = [q for q in ds.questions if (only is None or q.id in only) and q.id not in done]
    if limit is not None:
        todo = todo[:limit]
    tokens_used = sum(t["payload"]["usage"]["input_tokens"] + t["payload"]["usage"]["output_tokens"] for t in done.values())
    log(f"run '{config.label}': {len(todo)} to run, {len(done)} already done")

    consecutive_failures = 0
    for i, q in enumerate(todo, 1):
        if config.token_cap is not None and tokens_used >= config.token_cap:
            log(f"token cap {config.token_cap} reached: stopping with {len(todo) - i + 1} questions unrun")
            break
        if consecutive_failures >= config.abort_after:
            log(f"{consecutive_failures} questions in a row failed on the provider: stopping with "
                f"{len(todo) - i + 1} unrun. Re-run the same command later to resume.")
            break
        handle = handles[q.repo]
        store = Store(handle.db)
        error: str | None = None
        payload: dict[str, Any] | None = None
        events: list[dict[str, Any]] = []
        attempts = 0
        t0 = clock()
        try:
            for attempt in range(config.retries + 1):
                attempts = attempt + 1
                events, error, payload = [], None, None
                t0 = clock()
                try:
                    tools = ToolRunner(store, embedder, handle.root, config.search_k, config.max_result_chars)
                    agent = Agent(
                        llm_factory(), store, embedder, handle.root,
                        max_steps=config.max_steps, token_budget=config.token_budget, tools=tools,
                    )
                    for ev in agent.stream(q.question):
                        if ev.kind == "answer":
                            payload = ev.data["result"].to_dict()
                        else:
                            events.append({"t": round(clock() - t0, 2), "kind": ev.kind, **ev.data})
                    break
                except Exception as e:  # noqa: BLE001 - one bad question must never kill a long run
                    # A RuntimeError is a provider or network failure (worth retrying). Anything else is a
                    # bug: record it with its type and move on without retrying.
                    retryable = isinstance(e, RuntimeError)
                    error = (str(e) if retryable else f"{type(e).__name__}: {e}")[:300]
                    if not retryable or attempt >= config.retries:
                        break
                    sleep(config.retry_wait_s * (attempt + 1))
        finally:
            store.db.close()
        latency = round(clock() - t0, 2)

        if payload is not None:
            score = score_answer(q, payload).to_dict()
            used = payload["usage"]["input_tokens"] + payload["usage"]["output_tokens"]
            tokens_used += used
        else:  # keep the shape stable so aggregation never special-cases failures
            payload = {"answer": "", "stopped": "error", "steps": 0, "citations": {"valid": [], "invalid": [], "ungrounded": []},
                       "usage": {"input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0}}
            score = {"passed": False, "fact_pass": False, "evidence_hit": None if q.negative else False, "citations_ok": False,
                     "n_valid": 0, "n_invalid": 0, "n_ungrounded": 0, "avg_span": None, "missing_facts": list(q.facts),
                     "reasons": [f"provider error: {error}"]}
        trace = {"id": q.id, "repo": q.repo, "category": q.category, "negative": q.negative, "question": q.question,
                 "latency_s": latency, "attempts": attempts, "error": error, "payload": payload, "score": score,
                 "events": events, "config": config.label}
        with trace_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(trace, ensure_ascii=False) + "\n")
        consecutive_failures = consecutive_failures + 1 if error else 0
        done[q.id] = trace
        log(f"[{i}/{len(todo)}] {q.id} {'PASS' if score['passed'] else 'FAIL'} {latency:.1f}s"
            + (f"  ({'; '.join(score['reasons'])[:110]})" if not score["passed"] else ""))
        if config.min_interval_s and i < len(todo):
            sleep(config.min_interval_s)

    order = {q.id: n for n, q in enumerate(ds.questions)}
    return sorted(done.values(), key=lambda t: order.get(t["id"], 10**6))


def rescore_traces(ds: Dataset, traces: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Re-grade stored answers against the current dataset. Used after fixing a scoring mistake: no model calls."""
    by_id = {q.id: q for q in ds.questions}
    out: list[dict[str, Any]] = []
    for t in traces:
        q = by_id.get(t["id"])
        if q is None or t.get("error"):
            out.append(t)
            continue
        out.append({**t, "category": q.category, "negative": q.negative, "score": score_answer(q, t["payload"]).to_dict()})
    return out
