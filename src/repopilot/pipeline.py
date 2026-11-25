"""Index a cloned repo with a chunk cap so demos stay fast (decision #15)."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .embed import Embedder
from .ingest import chunk_repo
from .store import Store, path_prior

MAX_CHUNKS = 2500


@dataclass
class IndexSummary:
    chunks: int
    total_chunks_found: int
    truncated: bool


def build_index(
    root: Path,
    db: Path,
    embedder: Embedder,
    progress: Callable[[str, int, int], None] | None = None,
    max_chunks: int = MAX_CHUNKS,
) -> IndexSummary:
    def report(phase: str, done: int = 0, total: int = 0) -> None:
        if progress:
            progress(phase, done, total)

    report("chunking")
    chunks = chunk_repo(root)
    found = len(chunks)
    if found > max_chunks:  # keep source code first; stable sort preserves file order
        chunks = sorted(chunks, key=lambda c: -path_prior(c.path))[:max_chunks]
    db.parent.mkdir(parents=True, exist_ok=True)
    db.unlink(missing_ok=True)
    store = Store(db)
    store.add(chunks, embedder, progress=lambda d, t: report("embedding", d, t))
    store.db.close()
    return IndexSummary(len(chunks), found, found > len(chunks))
