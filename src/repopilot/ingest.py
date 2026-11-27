"""Clone a GitHub repo (shallow) and chunk every text source file."""
from __future__ import annotations

import os
import re
import shutil
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


CLONE_TIMEOUT_S = 120
MAX_REPO_BYTES = 200 * 1024 * 1024  # working tree only; a hosted instance has little disk


def _tree_bytes(root: Path) -> int:
    total = 0
    for p in root.rglob("*"):
        if ".git" in p.relative_to(root).parts or p.is_symlink():
            continue
        if p.is_file():
            total += p.stat().st_size
    return total


def clone(url: str, dest: Path) -> Path:
    validate_url(url)
    if not (dest / ".git").exists():
        # "--" stops option injection. Shallow, single-branch, no tags.
        # core.symlinks=false writes a repo's symlinks as plain text files, so a hostile repo cannot point the
        # indexer at files on this machine. GIT_TERMINAL_PROMPT=0 makes a private or missing repo fail instead
        # of waiting for a password.
        env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
        try:
            subprocess.run(
                ["git", "-c", "core.symlinks=false", "clone", "--depth", "1", "--single-branch", "--no-tags",
                 "--", url, str(dest)],
                check=True, capture_output=True, text=True, timeout=CLONE_TIMEOUT_S, env=env,
            )
        except subprocess.TimeoutExpired as e:
            shutil.rmtree(dest, ignore_errors=True)
            raise ValueError("This repository took too long to download. Try a smaller one.") from e
        except subprocess.CalledProcessError as e:
            shutil.rmtree(dest, ignore_errors=True)
            raise ValueError("Could not download this repository. Check that it exists and is public.") from e
        if _tree_bytes(dest) > MAX_REPO_BYTES:
            shutil.rmtree(dest, ignore_errors=True)
            raise ValueError("This repository is too large for the hosted app. Run RepoPilot locally to index it.")
    return dest


def iter_source_files(root: Path):
    for p in sorted(root.rglob("*")):
        if p.is_symlink() or not p.is_file() or any(part in SKIP_DIRS for part in p.relative_to(root).parts):
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
