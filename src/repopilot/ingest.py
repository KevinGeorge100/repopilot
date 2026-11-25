"""Clone a GitHub repo (shallow) and chunk every text source file."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from .chunker import Chunk, chunk_file

SKIP_DIRS = {".git", "node_modules", "dist", "build", ".venv", "venv", "__pycache__", "vendor", ".next", "target"}
SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".pdf", ".zip", ".lock", ".min.js", ".map", ".woff", ".woff2"}
MAX_FILE_BYTES = 300_000
# GitHub owners have no dots; repo names may, but are never "." or "..".
GITHUB_URL = re.compile(r"^https://github\.com/\w[\w-]*/(?!\.{1,2}(?:\.git)?/?$)[\w.-]+?(?:\.git)?/?$")


def validate_url(url: str) -> str:
    if not GITHUB_URL.match(url):
        raise ValueError("Only https://github.com/<owner>/<repo> URLs are supported")
    return url


def clone(url: str, dest: Path) -> Path:
    validate_url(url)
    if not (dest / ".git").exists():
        # "--" stops option injection; shallow clone keeps this fast.
        subprocess.run(
            ["git", "clone", "--depth", "1", "--", url, str(dest)],
            check=True, capture_output=True, text=True,
        )
    return dest


def iter_source_files(root: Path):
    for p in sorted(root.rglob("*")):
        if not p.is_file() or any(part in SKIP_DIRS for part in p.relative_to(root).parts):
            continue
        if p.suffix.lower() in SKIP_SUFFIXES or p.stat().st_size > MAX_FILE_BYTES:
            continue
        yield p


def chunk_repo(root: Path) -> list[Chunk]:
    chunks: list[Chunk] = []
    for p in iter_source_files(root):
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # binary or unreadable
        chunks.extend(chunk_file(str(p.relative_to(root)), text))
    return chunks
