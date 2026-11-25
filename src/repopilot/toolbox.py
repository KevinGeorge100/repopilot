"""Read-only tool definitions and the runner that executes them for any agent loop."""
from __future__ import annotations

import json
from pathlib import Path

from .citations import Citation, extract
from .embed import Embedder
from .llm import ToolUse
from .store import Store
from .tools import ToolError, list_tree, read_file, search_code

TOOL_SCHEMAS = [
    {
        "name": "search_code",
        "description": "Hybrid keyword+semantic search over the indexed repo. Returns chunks with path:start-end citations.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}, "k": {"type": "integer", "minimum": 1, "maximum": 20}},
            "required": ["query"],
        },
    },
    {
        "name": "read_file",
        "description": "Read lines of a file; output lines are prefixed with their line numbers.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "start_line": {"type": "integer", "minimum": 1},
                "end_line": {"type": "integer", "minimum": 1},
            },
            "required": ["path"],
        },
    },
    {
        "name": "list_tree",
        "description": "List a directory tree (depth 1-4).",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}, "depth": {"type": "integer", "minimum": 1, "maximum": 4}},
        },
    },
]

MAX_TOOL_RESULT_CHARS = 12_000


class ToolRunner:
    """Executes the three read-only tools. Output is framed as untrusted repository data."""

    def __init__(self, store: Store, embedder: Embedder, root: Path) -> None:
        self.store, self.embedder, self.root = store, embedder, root

    def run(self, tu: ToolUse, seen: list[Citation]) -> tuple[str, bool]:
        """Return (text for the model, is_error). Retrieved line ranges are appended to `seen`."""
        try:
            if tu.name == "search_code":
                res = search_code(self.store, self.embedder, str(tu.input.get("query", "")), int(tu.input.get("k", 8)))
                for h in res:
                    seen.extend(extract(h["citation"]))
            elif tu.name == "read_file":
                res = read_file(
                    self.root, str(tu.input.get("path", "")), int(tu.input.get("start_line", 1)), tu.input.get("end_line")
                )
                seen.extend(extract(res["citation"]))
            elif tu.name == "list_tree":
                res = list_tree(self.root, str(tu.input.get("path", ".")), int(tu.input.get("depth", 2)))
            else:
                return f"unknown tool: {tu.name}", True
        except (ToolError, ValueError, TypeError) as e:
            return f"error: {e}", True
        text = json.dumps(res, ensure_ascii=False)
        if len(text) > MAX_TOOL_RESULT_CHARS:
            text = text[:MAX_TOOL_RESULT_CHARS] + '..."[truncated]"'
        return f"<repository_data>\n{text}\n</repository_data>", False
