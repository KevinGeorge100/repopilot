"""Code-aware chunking: tree-sitter definitions with symbol names, with line-window fallback."""
from __future__ import annotations

from dataclasses import dataclass, replace

from tree_sitter_language_pack import detect_language_from_path, get_parser

DEF_HINTS = ("function", "method", "class", "struct", "impl", "interface", "enum", "trait")
CONTAINER_HINTS = ("class", "impl", "interface", "trait", "struct", "enum")
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
    symbol: str | None = None  # the function/class/method this chunk starts with, for exact-name retrieval

    @property
    def citation(self) -> str:
        return f"{self.path}:{self.start_line}-{self.end_line}"


def _window_chunks(
    path: str, lines: list[str], offset: int = 0, symbol: str | None = None, all_windows: bool = False
) -> list[Chunk]:
    """Overlapping line windows. `symbol` names the definition the first window starts; with `all_windows`
    every window belongs to that definition (a long function), so a question about code deep inside it still
    matches the function's name."""
    chunks, step = [], WINDOW - OVERLAP
    for i in range(0, max(len(lines), 1), step):
        block = lines[i : i + WINDOW]
        if not block or not "".join(block).strip():
            continue
        chunks.append(Chunk(path, offset + i + 1, offset + i + len(block), "\n".join(block), "window"))
        if i + WINDOW >= len(lines):
            break
    if symbol:
        for i in range(len(chunks) if all_windows else min(1, len(chunks))):
            chunks[i] = replace(chunks[i], symbol=symbol)
    return chunks


def _collect(node, out: list, depth: int = 0) -> None:
    if not node.is_named:  # keyword tokens such as `class` or `function` are not definitions
        return
    if any(h in node.type for h in DEF_HINTS) and node.end_point[0] > node.start_point[0] - 1:
        out.append(node)
        return
    if depth < 3:
        for child in node.children:
            _collect(child, out, depth + 1)


def _name(node, data: bytes) -> str | None:
    n = node.child_by_field_name("name") or node.child_by_field_name("type")  # Rust impl blocks have a type
    return data[n.start_byte : n.end_byte].decode("utf-8", "ignore") if n is not None else None


def _cover(path: str, lines: list[str], data: bytes, defs: list, lo: int, hi: int, container: str | None = None) -> list[Chunk]:
    """Chunk lines [lo, hi): one chunk per definition, windows for the code between them.

    A definition longer than MAX_LINES is split: a class into its methods (so each method is retrievable by
    name), anything else into windows.
    """
    out: list[Chunk] = []
    cursor = lo
    for node in sorted(defs, key=lambda n: n.start_point[0]):
        start, end = node.start_point[0], node.end_point[0]
        if start < cursor or end >= hi:
            continue
        if start > cursor:  # imports, constants, a class header: code between definitions
            lead_symbol = container if (cursor == lo and container) else None
            out.extend(_window_chunks(path, lines[cursor:start], cursor, lead_symbol))
        name = _name(node, data)
        if end - start + 1 <= MAX_LINES:
            out.append(Chunk(path, start + 1, end + 1, "\n".join(lines[start : end + 1]), "definition", name))
        else:
            nested: list = []
            if any(h in node.type for h in CONTAINER_HINTS):
                for child in node.children:
                    _collect(child, nested)
            if nested:
                out.extend(_cover(path, lines, data, nested, start, end + 1, name))
            else:
                out.extend(_window_chunks(path, lines[start : end + 1], start, name, all_windows=True))
        cursor = end + 1
    if cursor < hi:
        out.extend(_window_chunks(path, lines[cursor:hi], cursor, container if (cursor == lo and container) else None))
    return out


def chunk_file(path: str, source: str) -> list[Chunk]:
    """Split a source file into chunks with exact 1-indexed line ranges."""
    lines = source.splitlines()
    if not source.strip():
        return []
    lang = detect_language_from_path(path)
    if not lang:
        return _window_chunks(path, lines)
    data = source.encode()
    try:
        tree = get_parser(lang).parse(data)
    except Exception:  # noqa: BLE001 - any parser failure falls back to line windows
        return _window_chunks(path, lines)

    defs: list = []
    _collect(tree.root_node, defs)
    if not defs:
        return _window_chunks(path, lines)
    return _cover(path, lines, data, defs, 0, len(lines))
