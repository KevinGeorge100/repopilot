import json

import httpx
import pytest

from repopilot.agent import TOOL_SCHEMAS, Agent
from repopilot.chunker import chunk_file
from repopilot.embed import HashEmbedder
from repopilot.llm import (
    OpenAICompatLLM,
    TextBlock,
    ToolUse,
    make_llm,
    to_openai_messages,
    to_openai_tools,
)
from repopilot.store import Store


def client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def reply(content=None, tool_calls=None, usage=(11, 7)):
    msg = {"role": "assistant", "content": content}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    return httpx.Response(200, json={"choices": [{"message": msg}], "usage": {"prompt_tokens": usage[0], "completion_tokens": usage[1]}})


def llm_with(handler, **kw):
    return OpenAICompatLLM("https://x.test/v1/", "k", "m", client=client(handler), sleep=lambda s: None, **kw)


def test_transcript_conversion_roundtrip():
    msgs = [
        {"role": "user", "content": "q"},
        {"role": "assistant", "content": [{"type": "text", "text": "hi"}, {"type": "tool_use", "id": "c1", "name": "list_tree", "input": {"depth": 1}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "c1", "content": "data", "is_error": False}]},
    ]
    out = to_openai_messages("SYS", msgs)
    assert out[0] == {"role": "system", "content": "SYS"}
    assert out[2]["tool_calls"][0]["function"] == {"name": "list_tree", "arguments": '{"depth": 1}'}
    assert out[3] == {"role": "tool", "tool_call_id": "c1", "content": "data"}
    t = to_openai_tools(TOOL_SCHEMAS)
    assert t[0]["type"] == "function" and t[0]["function"]["parameters"]["required"] == ["query"]


def test_parses_text_and_tool_calls_and_usage():
    def handler(req):
        body = json.loads(req.content)
        assert req.url.path == "/v1/chat/completions" and req.headers["authorization"] == "Bearer k"
        assert body["model"] == "m" and body["tools"]
        return reply(None, [{"id": "a", "type": "function", "function": {"name": "search_code", "arguments": '{"query":"x"}'}}])

    r = llm_with(handler).create("s", [{"role": "user", "content": "q"}], TOOL_SCHEMAS)
    assert isinstance(r.content[0], ToolUse) and r.content[0].input == {"query": "x"}
    assert r.stop_reason == "tool_use" and (r.usage.input_tokens, r.usage.output_tokens) == (11, 7)
    r = llm_with(lambda req: reply("done")).create("s", [{"role": "user", "content": "q"}], [])
    assert r.content == [TextBlock("done")] and r.stop_reason == "end_turn"


def test_bad_tool_arguments_do_not_crash():
    h = lambda req: reply(None, [{"id": "a", "type": "function", "function": {"name": "list_tree", "arguments": "{not json"}}])
    assert llm_with(h).create("s", [], []).content[0].input == {}


def test_retries_429_with_retry_after_then_succeeds():
    calls, waits = [], []

    def handler(req):
        calls.append(1)
        return httpx.Response(429, headers={"retry-after": "3"}, text="slow down") if len(calls) < 3 else reply("ok")

    llm = OpenAICompatLLM("https://x.test/v1", "k", "m", client=client(handler), sleep=waits.append)
    assert llm.create("s", [], []).content == [TextBlock("ok")]
    assert waits == [3.0, 3.0]


def test_gives_up_after_max_retries_and_surfaces_errors():
    with pytest.raises(RuntimeError, match="429"):
        llm_with(lambda req: httpx.Response(429, text="no"), max_retries=2).create("s", [], [])
    with pytest.raises(RuntimeError, match="401"):
        llm_with(lambda req: httpx.Response(401, text="bad key")).create("s", [], [])


def test_agent_runs_end_to_end_over_openai_wire_format(tmp_path):
    src = "def parse_args(argv):\n    return argv[1:]\n"
    (tmp_path / "cli.py").write_text(src)
    emb, store = HashEmbedder(), Store()
    store.add(chunk_file("cli.py", src), emb)
    step = {"n": 0}

    def handler(req):
        step["n"] += 1
        if step["n"] == 1:
            return reply(None, [{"id": "t", "type": "function", "function": {"name": "search_code", "arguments": '{"query":"parse args"}'}}])
        msgs = json.loads(req.content)["messages"]
        assert msgs[-1]["role"] == "tool" and "<repository_data>" in msgs[-1]["content"]
        return reply("Args are parsed in `cli.py:1-2`.")

    r = Agent(llm_with(handler), store, emb, tmp_path).run("where are args parsed?")
    assert r.stopped == "done" and r.citations.ok


def test_make_llm_selection(monkeypatch):
    for k in ("GEMINI_API_KEY", "GROQ_API_KEY", "OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "REPOPILOT_PROVIDER", "REPOPILOT_MODEL"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        make_llm("gemini")
    with pytest.raises(RuntimeError, match="unknown provider"):
        make_llm("nope")
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    g = make_llm("gemini")
    assert isinstance(g, OpenAICompatLLM) and "generativelanguage.googleapis.com" in g.url
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    with pytest.raises(RuntimeError, match="REPOPILOT_MODEL"):
        make_llm("openrouter")
    monkeypatch.setenv("REPOPILOT_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "k")
    assert make_llm().model == "openai/gpt-oss-120b"


def test_gemini_thought_signature_is_echoed_back():
    sig = {"google": {"thought_signature": "abc"}}
    tc = [{"id": "a", "type": "function", "extra_content": sig, "function": {"name": "list_tree", "arguments": "{}"}}]
    r = llm_with(lambda req: reply(None, tc)).create("s", [], [])
    assert r.content[0].extra == sig
    from repopilot.llm import block_to_param

    msgs = [{"role": "assistant", "content": [block_to_param(r.content[0])]}]
    assert to_openai_messages("S", msgs)[1]["tool_calls"][0]["extra_content"] == sig


def test_network_errors_retry_then_become_runtime_error():
    def boom(req):
        raise httpx.ReadTimeout("slow")

    with pytest.raises(RuntimeError, match="unreachable"):
        llm_with(boom, max_retries=1).create("s", [], [])
