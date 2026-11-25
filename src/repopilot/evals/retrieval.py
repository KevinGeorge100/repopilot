"""Retrieval-only evaluation: does the evidence land in the top results? No model calls, so it is free and exact."""
from __future__ import annotations

from dataclasses import dataclass, replace
from statistics import mean

from ..embed import Embedder
from ..store import Store
from .dataset import Dataset, Question
from .runner import RepoHandle

DEPTH = 20


@dataclass
class RetrievalResult:
    id: str
    repo: str
    rank: int | None  # 1-based rank of the first chunk overlapping gold evidence, None if outside the top DEPTH


def first_hit_rank(store: Store, embedder: Embedder, q: Question, depth: int = DEPTH) -> int | None:
    hits = store.search(q.question, embedder, depth)
    for rank, h in enumerate(hits, 1):
        c = h.chunk
        if any(c.path == g.path and c.start_line <= g.end and g.start <= c.end_line for g in q.gold):
            return rank
    return None


def evaluate_retrieval(
    ds: Dataset, handles: dict[str, RepoHandle], embedder: Embedder, symbols: bool = True
) -> list[RetrievalResult]:
    """Search with each positive question's own text and find where the gold evidence ranks.

    `symbols=False` switches off name matching on the same index, for an exact before/after of that ranker.
    """
    out: list[RetrievalResult] = []
    for repo, handle in handles.items():
        store = Store(handle.db)
        store.has_symbols = store.has_symbols and symbols
        try:
            for q in ds.questions:
                if q.repo == repo and not q.negative:
                    out.append(RetrievalResult(q.id, repo, first_hit_rank(store, embedder, q)))
        finally:
            store.db.close()
    return out


def summarize(results: list[RetrievalResult]) -> dict:
    n = len(results)

    def at(k: int) -> float | None:
        return sum(1 for r in results if r.rank is not None and r.rank <= k) / n if n else None

    return {
        "n": n,
        "hit@1": at(1),
        "hit@3": at(3),
        "hit@8": at(8),
        "hit@20": at(DEPTH),
        "mrr": mean((1 / r.rank if r.rank else 0.0) for r in results) if n else None,
        "missed": [r.id for r in results if r.rank is None],
    }


def evaluate_queries(
    ds: Dataset,
    handles: dict[str, RepoHandle],
    embedder: Embedder,
    traces: list[dict],
    symbols: bool = True,
) -> list[RetrievalResult]:
    """Replay the search queries a past run actually issued, to see whether the evidence now surfaces for them.

    Each question scores the best rank over all of its queries, so a thrashing run is judged by whether ANY of its
    repeated attempts would have found the evidence. Questions the agent never searched for are skipped.
    """
    by_id = {q.id: q for q in ds.questions}
    out: list[RetrievalResult] = []
    stores: dict[str, Store] = {}
    try:
        for t in traces:
            q = by_id.get(t["id"])
            queries = [e["input"].get("query", "") for e in t.get("events", []) if e.get("kind") == "tool_call" and e.get("name") == "search_code"]
            if q is None or q.negative or not queries:
                continue
            if q.repo not in stores:
                stores[q.repo] = Store(handles[q.repo].db)
                stores[q.repo].has_symbols = stores[q.repo].has_symbols and symbols
            ranks = [r for query in dict.fromkeys(queries) if (r := first_hit_rank(stores[q.repo], embedder, replace(q, question=str(query)))) is not None]
            out.append(RetrievalResult(q.id, q.repo, min(ranks) if ranks else None))
    finally:
        for s in stores.values():
            s.db.close()
    return out
