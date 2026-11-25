"""SQLite store: FTS5 (BM25) + vector blobs, fused with reciprocal rank fusion (decision #4)."""
from __future__ import annotations

import re
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .chunker import Chunk
from .embed import Embedder

RRF_K = 60
EMBED_CHARS = 1000  # measured: 1000 keeps recall@8 of 1500 and builds a third faster (see evals/RESULTS.md)
INDEX_VERSION = 3  # 3: every window of a long function carries its symbol, embeds 1000 chars (2: symbols, class splitting)


@dataclass(frozen=True)
class Hit:
    chunk: Chunk
    score: float


DOC_SUFFIXES = (".md", ".rst", ".txt", ".adoc")


def path_prior(path: str) -> float:
    """Prefer source over docs over changelogs (decision: code Q&A is the product)."""
    low = path.lower()
    if "changelog" in low or "changes" in low.rsplit("/", 1)[-1] or "history" in low.rsplit("/", 1)[-1]:
        return 0.4
    if low.endswith(DOC_SUFFIXES) or low.startswith(("docs/", "doc/", "examples/")):
        return 0.7
    return 1.0


def _fts_query(q: str) -> str:
    """Turn free text into a safe FTS5 OR-query (quote every token)."""
    toks = re.findall(r"[A-Za-z0-9_]+", q)
    return " OR ".join(f'"{t}"' for t in toks)


class Store:
    def __init__(self, path: str | Path = ":memory:") -> None:
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS chunks(
              id INTEGER PRIMARY KEY, path TEXT, start_line INT, end_line INT,
              kind TEXT, text TEXT, vec BLOB, symbol TEXT);
            CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
              text, path, content='chunks', content_rowid='id', tokenize="unicode61 tokenchars '_'");
            """
        )
        # Indexes built before symbols existed have no such column: they keep working, without name matching.
        self.has_symbols = "symbol" in {r[1] for r in self.db.execute("PRAGMA table_info(chunks)")}
        if self.has_symbols:
            self.db.execute("CREATE INDEX IF NOT EXISTS chunks_symbol ON chunks(symbol)")

    def add(
        self,
        chunks: list[Chunk],
        embedder: Embedder,
        batch: int = 32,
        progress: Callable[[int, int], None] | None = None,
        embed_chars: int = EMBED_CHARS,
    ) -> None:
        """Embed and store chunks. Only the first `embed_chars` characters are embedded (cost grows steeply with
        length); keyword and name search still see the whole chunk."""
        for i in range(0, len(chunks), batch):
            part = chunks[i : i + batch]
            vecs = embedder.embed([f"{c.path}\n{c.text}"[:embed_chars] for c in part])
            for c, v in zip(part, vecs, strict=True):
                cur = self.db.execute(
                    "INSERT INTO chunks(path,start_line,end_line,kind,text,vec,symbol) VALUES(?,?,?,?,?,?,?)",
                    (c.path, c.start_line, c.end_line, c.kind, c.text, v.astype(np.float32).tobytes(), c.symbol),
                )
                self.db.execute(
                    "INSERT INTO chunks_fts(rowid,text,path) VALUES(?,?,?)", (cur.lastrowid, c.text, c.path)
                )
            if progress:
                progress(min(i + batch, len(chunks)), len(chunks))
        self.db.commit()

    def count(self) -> int:
        return self.db.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]

    def _row_chunk(self, row) -> Chunk:
        symbol = row[7] if len(row) > 7 else None
        return Chunk(path=row[1], start_line=row[2], end_line=row[3], kind=row[4], text=row[5], symbol=symbol)

    def search(self, query: str, embedder: Embedder, k: int = 8) -> list[Hit]:
        pool = max(k * 4, 20)
        ranks: dict[int, float] = {}

        fq = _fts_query(query)
        if fq:
            for r, (rid,) in enumerate(
                self.db.execute(
                    "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH ? ORDER BY bm25(chunks_fts, 1.0, 0.3) LIMIT ?",
                    (fq, pool),
                )
            ):
                ranks[rid] = ranks.get(rid, 0.0) + 1.0 / (RRF_K + r + 1)

        rows = self.db.execute("SELECT id, vec FROM chunks").fetchall()
        if rows:
            ids = np.array([r[0] for r in rows])
            mat = np.vstack([np.frombuffer(r[1], dtype=np.float32) for r in rows])
            sims = mat @ embedder.embed([query])[0]
            for r, idx in enumerate(np.argsort(-sims)[:pool]):
                rid = int(ids[idx])
                ranks[rid] = ranks.get(rid, 0.0) + 1.0 / (RRF_K + r + 1)

        # Third signal: a chunk that DEFINES a name the question mentions. Keyword and vector search drown a
        # definition in the tests and docs that merely use the name; this brings it back to the top.
        names = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]+", query))
        if self.has_symbols and names:
            marks = ",".join("?" * len(names))
            named = self.db.execute(f"SELECT id, path FROM chunks WHERE symbol IN ({marks})", tuple(names)).fetchall()
            named.sort(key=lambda row: (-path_prior(row[1]), row[0]))
            for r, (rid, _) in enumerate(named[:pool]):
                ranks[rid] = ranks.get(rid, 0.0) + 1.0 / (RRF_K + r + 1)

        hits = []
        for rid, score in ranks.items():
            row = self.db.execute("SELECT * FROM chunks WHERE id=?", (rid,)).fetchone()
            hits.append(Hit(self._row_chunk(row), score * path_prior(row[1])))
        return sorted(hits, key=lambda h: -h.score)[:k]
