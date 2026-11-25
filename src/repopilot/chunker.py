"""Code-aware chunking: tree-sitter definitions, with line-window fallback."""
from __future__ import annotations

from dataclasses import dataclass

from tree_sitter_language_pack import detect_language_from_path, get_parser

DEF_HINTS = ("function", "method", "class", "struct", "impl", "interface", "enum", "trait")
MAX_LINES = 80
WINDOW = 60
OVERLAP = 10


@dataclass(frozen=True)
class Chunk:
    path: str
    start_line: int  # 1-indexed, inclusive
    end_line: int  # 1-indexed, inclusive
    text: str
    kind: str  # "definition" | "window"

    @property
    def citation(self) -> str:
        return f"{self.path}:{self.start_line}-{self.end_line}"


def _window_chunks(path: str, lines: list[str], offset: int = 0) -> list[Chunk]:
    chunks, step = [], WINDOW - OVERLAP
    for i in range(0, max(len(lines), 1), step):
        block = lines[i : i + WINDOW]
        if not block or not "".join(block).strip():
            continue
        chunks.append(
            Chunk(path, offset + i + 1, offset + i + len(block), "\n".join(block), "window")
        )
        if i + WINDOW >= len(lines):
            break
    return chunks


def _collect(node, out: list, depth: int = 0) -> None:
    if any(h in node.type for h in DEF_HINTS) and node.end_point[0] > node.start_point[0] - 1:
        out.append(node)
        return
    if depth < 3:
        for child in node.children:
            _collect(child, out, depth + 1)


def chunk_file(path: str, source: str) -> list[Chunk]:
    """Split a source file into chunks with exact 1-indexed line ranges."""
    lines = source.splitlines()
    if not source.strip():
        return []
    lang = detect_language_from_path(path)
    if not lang:
        return _window_chunks(path, lines)
    try:
        tree = get_parser(lang).parse(source.encode())
    except Exception:  # noqa: BLE001 - any parser failure falls back to line windows
        return _window_chunks(path, lines)

    defs: list = []
    _collect(tree.root_node, defs)
    if not defs:
        return _window_chunks(path, lines)

    chunks: list[Chunk] = []
    cursor = 0  # 0-indexed line already covered
    for node in sorted(defs, key=lambda n: n.start_point[0]):
        start, end = node.start_point[0], node.end_point[0]
        if start < cursor:
            continue
        if start > cursor:  # gap code (imports, constants) between definitions
            chunks.extend(_window_chunks(path, lines[cursor:start], cursor))
        body = lines[start : end + 1]
        if len(body) > MAX_LINES:
            chunks.extend(_window_chunks(path, body, start))
        else:
            chunks.append(Chunk(path, start + 1, end + 1, "\n".join(body), "definition"))
        cursor = end + 1
    if cursor < len(lines):
        chunks.extend(_window_chunks(path, lines[cursor:], cursor))
    return chunks
