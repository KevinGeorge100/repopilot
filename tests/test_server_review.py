import json

from diffs import SAMPLE_DIFF
from fastapi.testclient import TestClient

from repopilot.embed import HashEmbedder
from repopilot.llm import LLMResponse, StubLLM, ToolUse, Usage
from repopilot.server import create_app

URL = "https://github.com/acme/demo/pull/7"
FINDING = {
    "path": "app.py", "start_line": 5, "end_line": 6, "severity": "security",
    "title": "eval on file contents", "explanation": "Runs arbitrary code from the file.",
}


def make(tmp_path, diff_fn=lambda o, r, n: SAMPLE_DIFF, ask_limit=12):
    def llm_factory():
        return StubLLM([LLMResponse([ToolUse("s", "submit_review", {"summary": "Adds eval.", "findings": [FINDING]})], "tool_use", Usage(10, 5))])

    return TestClient(create_app(tmp_path, llm_factory, HashEmbedder(), lambda u, d: d, diff_fn, ask_limit))


def parse_sse(text):
    out = []
    for block in text.strip().split("\n\n"):
        ev, data = block.split("\n", 1)
        out.append((ev.removeprefix("event: "), json.loads(data.removeprefix("data: "))))
    return out


def test_review_streams_structured_result(tmp_path):
    r = make(tmp_path).post("/api/review", json={"url": URL})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(r.text)
    kind, data = events[-1]
    assert kind == "review" and data["stopped"] == "done" and data["context"] is False
    assert data["findings"][0]["path"] == "app.py" and data["summary"] == "Adds eval."


def test_review_input_errors(tmp_path):
    c = make(tmp_path)
    assert c.post("/api/review", json={"url": "https://evil.com/a/b/pull/1"}).status_code == 400
    assert c.post("/api/review", json={"url": "https://github.com/a/b/issues/1"}).status_code == 400

    def not_found(o, r, n):
        raise ValueError("Pull request not found. It must be public.")

    assert make(tmp_path, not_found).post("/api/review", json={"url": URL}).status_code == 422

    def down(o, r, n):
        raise RuntimeError("Could not download the diff: ConnectError")

    assert make(tmp_path, down).post("/api/review", json={"url": URL}).status_code == 502
    assert make(tmp_path, lambda o, r, n: "no diff here").post("/api/review", json={"url": URL}).status_code == 422


def test_review_is_rate_limited(tmp_path):
    c = make(tmp_path, ask_limit=1)
    assert c.post("/api/review", json={"url": URL}).status_code == 200
    assert c.post("/api/review", json={"url": URL}).status_code == 429
