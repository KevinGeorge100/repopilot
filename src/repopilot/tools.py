"""Read-only agent tools (decision #7). Repo content is untrusted data."""
from __future__ import annotations

from pathlib import Path

from .embed import Embedder
from .ingest import SKIP_DIRS
from .store import Store

MAX_READ_LINES = 400
MAX_TREE_ENTRIES = 300


class ToolError(ValueError):
    """Bad tool input; message is safe to show the model."""


def _resolve(root: Path, rel: str) -> Path:
    root = root.resolve()
    p = (root / rel).resolve()
    if p != root and root not in p.parents:
        raise ToolError("path escapes the repository")
    if any(part in SKIP_DIRS for part in p.relative_to(root).parts):
        raise ToolError("path is excluded from the index")
    return p


def search_code(store: Store, embedder: Embedder, query: str, k: int = 8) -> list[dict]:
    if not query.strip():
        raise ToolError("query is empty")
    return [
        {
            "citation": h.chunk.citation,
            "kind": h.chunk.kind,
            "score": round(h.score, 4),
            # numbered like read_file, so answers can cite the exact lines that matter
            "text": "\n".join(f"{h.chunk.start_line + i}: {ln}" for i, ln in enumerate(h.chunk.text.splitlines())),
        }
        for h in store.search(query, embedder, min(max(k, 1), 20))
    ]


def read_file(root: Path, path: str, start_line: int = 1, end_line: int | None = None) -> dict:
    p = _resolve(root, path)
    if not p.is_file():
        raise ToolError(f"not a file: {path}")
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError as e:
        raise ToolError("file is not UTF-8 text") from e
    start = max(start_line, 1)
    end = min(end_line or len(lines), len(lines), start + MAX_READ_LINES - 1)
    if start > len(lines):
        raise ToolError(f"file has only {len(lines)} lines")
    body = lines[start - 1 : end]
    return {
        "citation": f"{path}:{start}-{end}",
        "total_lines": len(lines),
        "text": "\n".join(f"{start + i}: {ln}" for i, ln in enumerate(body)),
    }


def list_tree(root: Path, path: str = ".", depth: int = 2) -> dict:
    base = _resolve(root, path)
    if not base.is_dir():
        raise ToolError(f"not a directory: {path}")
    root = root.resolve()
    out: list[str] = []

    def walk(d: Path, level: int) -> None:
        for p in sorted(d.iterdir(), key=lambda x: (x.is_file(), x.name)):
            if p.name in SKIP_DIRS or len(out) >= MAX_TREE_ENTRIES:
                continue
            out.append(("  " * level) + p.name + ("/" if p.is_dir() else ""))
            if p.is_dir() and level + 1 < min(max(depth, 1), 4):
                walk(p, level + 1)

    walk(base, 0)
    return {"path": str(base.relative_to(root)) or ".", "entries": out, "truncated": len(out) >= MAX_TREE_ENTRIES}
