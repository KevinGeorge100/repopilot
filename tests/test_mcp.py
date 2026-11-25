import asyncio
import sys
from pathlib import Path

import pytest
from diffs import SAMPLE_DIFF
from mcp import Client, StdioServerParameters

from repopilot.embed import HashEmbedder
from repopilot.llm import LLMResponse, StubLLM, TextBlock, ToolUse, Usage
from repopilot.mcp_server import build_server, resolve_repo

URL = "https://github.com/acme/demo"
SRC = "def hello():\n    '''Say hello.'''\n    return 1\n\n\ndef goodbye():\n    return 2\n"
FINDING = {
    "path": "app.py", "start_line": 4, "end_line": 5, "severity": "security",
    "title": "eval on file contents", "explanation": "Runs arbitrary code from the file.",
}


def fake_clone(url, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "a.py").write_text(SRC)
    (dest / "README.md").write_text("# demo\n")
    return dest


def llm_factory():
    return StubLLM(
        [
            LLMResponse([ToolUse("t", "search_code", {"query": "hello"})], "tool_use", Usage(10, 2)),
            LLMResponse([TextBlock("hello returns 1 (`a.py:1-3`).")], "end_turn", Usage(10, 6)),
        ]
    )


def review_llm():
    return StubLLM([LLMResponse([ToolUse("s", "submit_review", {"summary": "Adds eval.", "findings": [FINDING]})], "tool_use", Usage(5, 5))])


def server(tmp_path, llm=llm_factory):
    return build_server(tmp_path, HashEmbedder(), fake_clone, llm, lambda o, r, n: SAMPLE_DIFF)


async def wait_ready(c, repo="acme/demo"):
    for _ in range(200):
        st = (await c.call_tool("repo_status", {"repo": repo})).structured_content
        if st["status"] in ("ready", "error"):
            return st
        await asyncio.sleep(0.05)
    raise AssertionError("indexing did not finish")


def test_tool_list_and_annotations(tmp_path):
    async def main():
        async with Client(server(tmp_path)) as c:
            return {t.name: t for t in (await c.list_tools()).tools}

    tools = asyncio.run(main())
    assert set(tools) == {"index_repo", "repo_status", "search_code", "read_file", "list_tree", "ask_repo", "review_pr"}
    assert tools["index_repo"].annotations.read_only_hint is False
    assert all(t.annotations.read_only_hint for n, t in tools.items() if n != "index_repo")


def test_index_search_read_list_flow(tmp_path):
    async def main():
        async with Client(server(tmp_path)) as c:
            assert "untrusted data" in c.instructions
            r = await c.call_tool("index_repo", {"url": URL})
            assert r.structured_content["repo"] == "acme/demo" and not r.is_error
            st = await wait_ready(c)
            assert st["status"] == "ready" and st["chunks"] >= 2 and "ready" in st["next"].lower()
            hits = (await c.call_tool("search_code", {"repo": "acme/demo", "query": "say hello", "k": 3})).structured_content
            rd = (await c.call_tool("read_file", {"repo": "acme/demo", "path": "a.py", "start_line": 1, "end_line": 2})).structured_content
            tree = (await c.call_tool("list_tree", {"repo": "acme--demo"})).structured_content
            again = (await c.call_tool("index_repo", {"url": URL})).structured_content
            return hits, rd, tree, again

    hits, rd, tree, again = asyncio.run(main())
    res = hits.get("result", hits)
    assert res[0]["citation"].startswith("a.py:") and res[0]["text"].startswith("1: def hello")
    assert rd["citation"] == "a.py:1-2" and rd["text"].startswith("1: def hello")
    assert "a.py" in " ".join(tree["entries"])
    assert again["status"] == "ready"  # idempotent


def test_errors_are_visible_to_the_model(tmp_path):
    async def main():
        async with Client(server(tmp_path)) as c:
            out = {}
            out["not_indexed"] = await c.call_tool("search_code", {"repo": "nope/none", "query": "x"})
            out["bad_name"] = await c.call_tool("read_file", {"repo": "bad repo", "path": "a"})
            out["bad_url"] = await c.call_tool("index_repo", {"url": "https://evil.com/a/b"})
            out["status"] = await c.call_tool("repo_status", {"repo": "nope/none"})
            await c.call_tool("index_repo", {"url": URL})
            await wait_ready(c)
            out["escape"] = await c.call_tool("read_file", {"repo": "acme/demo", "path": "../../etc/passwd"})
            return out

    out = asyncio.run(main())
    assert all(r.is_error for r in out.values())
    assert "Call index_repo first" in out["not_indexed"].content[0].text
    assert "owner/name" in out["bad_name"].content[0].text
    assert "github.com" in out["bad_url"].content[0].text
    assert "escapes the repository" in out["escape"].content[0].text
    assert "Error executing tool" in out["escape"].content[0].text and "Traceback" not in out["escape"].content[0].text


def test_ask_repo_returns_verified_citations(tmp_path):
    async def main():
        async with Client(server(tmp_path)) as c:
            await c.call_tool("index_repo", {"url": URL})
            await wait_ready(c)
            return await c.call_tool("ask_repo", {"repo": "acme/demo", "question": "What does hello return?"})

    r = asyncio.run(main()).structured_content
    assert r["stopped"] == "done" and r["citations"]["ok"] and r["citations"]["valid"][0]["path"] == "a.py"


def test_review_pr_with_and_without_repo_context(tmp_path):
    async def main():
        async with Client(server(tmp_path, review_llm)) as c:
            first = await c.call_tool("review_pr", {"url": f"{URL}/pull/7"})
            await c.call_tool("index_repo", {"url": URL})
            await wait_ready(c)
            second = await c.call_tool("review_pr", {"url": f"{URL}/pull/7"})
            bad = await c.call_tool("review_pr", {"url": "https://github.com/acme/demo/issues/7"})
            return first, second, bad

    first, second, bad = asyncio.run(main())
    assert first.structured_content["context"] is False and second.structured_content["context"] is True
    assert first.structured_content["findings"][0]["path"] == "app.py"
    assert bad.is_error and "pull request URL" in bad.content[0].text


def test_missing_llm_key_is_a_clear_tool_error(tmp_path):
    def no_key():
        raise RuntimeError("GEMINI_API_KEY is not set")

    async def main():
        async with Client(server(tmp_path, no_key)) as c:
            await c.call_tool("index_repo", {"url": URL})
            await wait_ready(c)
            return await c.call_tool("ask_repo", {"repo": "acme/demo", "question": "hello?"})

    r = asyncio.run(main())
    assert r.is_error and "GEMINI_API_KEY is not set" in r.content[0].text


@pytest.mark.parametrize(
    ("raw", "rid"),
    [("pallets/click", "pallets--click"), ("pallets--click", "pallets--click"), ("https://github.com/pallets/click.git", "pallets--click")],
)
def test_resolve_repo_accepts_three_forms(raw, rid):
    assert resolve_repo(raw) == rid


@pytest.mark.parametrize("raw", ["", "click", "a/b/c/../x", "../etc"])
def test_resolve_repo_rejects_junk(raw):
    with pytest.raises(ValueError):
        resolve_repo(raw)


def test_real_stdio_entrypoint_speaks_clean_mcp(tmp_path):
    """Launch `repopilot mcp` as a subprocess, exactly as Claude Code would; stdout must be pure protocol."""
    params = StdioServerParameters(command=sys.executable, args=["-m", "repopilot.cli", "mcp", "--workdir", str(tmp_path)])

    async def main():
        async with Client(params) as c:
            tools = {t.name for t in (await c.list_tools()).tools}
            st = await c.call_tool("repo_status", {"repo": "nope/none"})
            return tools, st

    tools, st = asyncio.run(asyncio.wait_for(main(), 60))
    assert "search_code" in tools and "review_pr" in tools and st.is_error
