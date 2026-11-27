"""Index a cloned repo with a chunk cap so demos stay fast (decision #15)."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .embed import Embedder
from .ingest import chunk_repo
from .store import EMBED_CHARS, Store, path_prior

MAX_CHUNKS = 2500


@dataclass
class IndexSummary:
    chunks: int
    total_chunks_found: int
    truncated: bool


def build_text_index(root: Path, db: Path, max_chunks: int = MAX_CHUNKS) -> IndexSummary:
    """Chunk a repo and store it for keyword and name search. Takes a second or two; questions can be asked at once."""
    chunks = chunk_repo(root)
    found = len(chunks)
    if found > max_chunks:  # keep source code first; stable sort preserves file order
        chunks = sorted(chunks, key=lambda c: -path_prior(c.path))[:max_chunks]
    db.parent.mkdir(parents=True, exist_ok=True)
    for suffix in ("", "-wal", "-shm"):
        Path(str(db) + suffix).unlink(missing_ok=True)
    store = Store(db)
    store.add_text(chunks)
    store.db.close()
    return IndexSummary(len(chunks), found, found > len(chunks))


def embed_index(
    db: Path,
    embedder: Embedder,
    progress: Callable[[int, int], None] | None = None,
    embed_chars: int = EMBED_CHARS,
) -> None:
    """Add vectors to an index built by build_text_index (slow: runs the embedding model)."""
    store = Store(db)
    try:
        store.embed_pending(embedder, progress, embed_chars)
    finally:
        store.db.close()


def build_index(
    root: Path,
    db: Path,
    embedder: Embedder,
    progress: Callable[[str, int, int], None] | None = None,
    max_chunks: int = MAX_CHUNKS,
    embed_chars: int = EMBED_CHARS,
) -> IndexSummary:
    """Both steps in one call (CLI, evaluation, demo seeding)."""
    if progress:
        progress("chunking", 0, 0)
    summary = build_text_index(root, db, max_chunks)
    embed_index(db, embedder, lambda d, t: progress and progress("embedding", d, t), embed_chars)
    return summary
