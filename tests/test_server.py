import json
import shutil
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from repopilot.embed import HashEmbedder
from repopilot.llm import LLMResponse, StubLLM, TextBlock, ToolUse, Usage
from repopilot.pipeline import build_index
from repopilot.server import RateLimiter, create_app, repo_id_from_url

SRC = "def parse_args(argv):\n    '''Parse CLI args.'''\n    return argv[1:]\n\n\ndef main():\n    return parse_args([])\n"
URL = "https://github.com/acme/demo"


@pytest.fixture
def fixture_repo(tmp_path: Path) -> Path:
    d = tmp_path / "fixture"
    d.mkdir()
    (d / "cli.py").write_text(SRC)
    (d / "README.md").write_text("# demo\n")
    return d


def make_client(tmp_path, fixture_repo, script=None, **kw):
    def fake_clone(url, dest):
        shutil.copytree(fixture_repo, dest, dirs_exist_ok=True)
        return dest

    def llm_factory():
        return StubLLM(
            script
            or [
                LLMResponse([ToolUse("t", "search_code", {"query": "parse args"})], "tool_use", Usage(50, 5)),
                LLMResponse([TextBlock("Args are parsed in `cli.py:1-3`.")], "end_turn", Usage(60, 9)),
            ]
        )

    app = create_app(tmp_path / "work", llm_factory, HashEmbedder(), fake_clone, **kw)
    return TestClient(app)


def wait_ready(c, rid, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        st = c.get(f"/api/repos/{rid}").json()
        if st["status"] in ("ready", "error"):
            return st
        time.sleep(0.05)
    raise AssertionError("indexing did not finish")


def parse_sse(text: str):
    out = []
    for block in text.strip().split("\n\n"):
        ev, data = block.split("\n", 1)
        out.append((ev.removeprefix("event: "), json.loads(data.removeprefix("data: "))))
    return out


def test_repo_id_and_url_validation():
    assert repo_id_from_url(URL) == "acme--demo"
    assert repo_id_from_url("https://github.com/a/b.git/") == "a--b"
    with pytest.raises(ValueError):
        repo_id_from_url("https://evil.com/a/b")


def test_index_then_ask_streams_cited_answer(tmp_path, fixture_repo):
    c = make_client(tmp_path, fixture_repo)
    r = c.post("/api/repos", json={"url": URL})
    assert r.status_code == 202 and r.json()["id"] == "acme--demo"
    st = wait_ready(c, "acme--demo")
    assert st["status"] == "ready" and st["chunks"] >= 2

    resp = c.post("/api/ask", json={"repo": "acme--demo", "question": "where are args parsed?"})
    assert resp.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(resp.text)
    kinds = [k for k, _ in events]
    assert kinds == ["tool_call", "tool_result", "answer"]
    ans = events[-1][1]
    assert ans["stopped"] == "done" and ans["citations"]["ok"]
    assert ans["citations"]["valid"] == [{"path": "cli.py", "start": 1, "end": 3}]
    assert ans["usage"]["input_tokens"] == 110


def test_index_is_idempotent_and_survives_restart(tmp_path, fixture_repo):
    c = make_client(tmp_path, fixture_repo)
    c.post("/api/repos", json={"url": URL})
    wait_ready(c, "acme--demo")
    again = c.post("/api/repos", json={"url": URL}).json()
    assert again["status"] == "ready"
    c2 = make_client(tmp_path, fixture_repo)  # fresh process, same workdir
    assert c2.get("/api/repos/acme--demo").json()["status"] == "ready"
    assert c2.post("/api/repos", json={"url": URL}).json()["status"] == "ready"


def test_bad_inputs(tmp_path, fixture_repo):
    c = make_client(tmp_path, fixture_repo)
    assert c.post("/api/repos", json={"url": "https://evil.com/a/b"}).status_code == 400
    assert c.post("/api/repos", json={"url": "--upload-pack=x"}).status_code == 400
    assert c.get("/api/repos/..%2Fetc").status_code in (400, 404)
    assert c.get("/api/repos/nope--nope").status_code == 404
    assert c.post("/api/ask", json={"repo": "nope--nope", "question": "hello?"}).status_code == 404
    assert c.post("/api/ask", json={"repo": "x", "question": "hi"}).status_code == 422


def test_clone_failure_reports_error_status(tmp_path, fixture_repo):
    def bad_clone(url, dest):
        raise RuntimeError("repository not found")

    app = create_app(tmp_path / "w", lambda: StubLLM([]), HashEmbedder(), bad_clone)
    c = TestClient(app)
    c.post("/api/repos", json={"url": URL})
    st = wait_ready(c, "acme--demo")
    assert st["status"] == "error" and "repository not found" in st["error"]


def test_file_endpoint_returns_lines_and_blocks_traversal(tmp_path, fixture_repo):
    c = make_client(tmp_path, fixture_repo)
    c.post("/api/repos", json={"url": URL})
    wait_ready(c, "acme--demo")
    r = c.get("/api/repos/acme--demo/file", params={"path": "cli.py", "start": 1, "end": 3}).json()
    assert r["lines"][0] == "def parse_args(argv):" and r["total"] == 7 and r["end"] == 3
    for bad in ["../../etc/passwd", "/etc/passwd", ".git/config"]:
        assert c.get("/api/repos/acme--demo/file", params={"path": bad}).status_code == 404


def test_llm_not_configured_is_503_and_provider_errors_stream_as_error_event(tmp_path, fixture_repo):
    c = make_client(tmp_path, fixture_repo)
    c.post("/api/repos", json={"url": URL})
    wait_ready(c, "acme--demo")

    def no_key():
        raise RuntimeError("GEMINI_API_KEY is not set")

    app = create_app(tmp_path / "work", no_key, HashEmbedder(), lambda u, d: d)
    assert TestClient(app).post("/api/ask", json={"repo": "acme--demo", "question": "hello?"}).status_code == 503

    class Boom:
        def create(self, *a):
            raise RuntimeError("LLM provider error 429")

    app = create_app(tmp_path / "work", lambda: Boom(), HashEmbedder(), lambda u, d: d)
    events = parse_sse(TestClient(app).post("/api/ask", json={"repo": "acme--demo", "question": "hello?"}).text)
    assert events[-1][0] == "error" and "429" in events[-1][1]["message"]


def test_ask_rate_limit(tmp_path, fixture_repo):
    c = make_client(tmp_path, fixture_repo, ask_limit=2)
    c.post("/api/repos", json={"url": URL})
    wait_ready(c, "acme--demo")
    body = {"repo": "acme--demo", "question": "where are args parsed?"}
    assert c.post("/api/ask", json=body).status_code == 200
    assert c.post("/api/ask", json=body).status_code == 200
    assert c.post("/api/ask", json=body).status_code == 429


def test_rate_limiter_window():
    t = [0.0]
    rl = RateLimiter(clock=lambda: t[0])
    assert rl.allow("k", 2, 10) and rl.allow("k", 2, 10) and not rl.allow("k", 2, 10)
    t[0] = 11.0
    assert rl.allow("k", 2, 10) and rl.allow("other", 1, 10)


def test_chunk_cap_keeps_source_and_flags_truncation(tmp_path):
    root = tmp_path / "r"
    root.mkdir()
    (root / "a.py").write_text(SRC)
    for i in range(5):
        (root / f"CHANGES{i}.md").write_text(f"# change {i}\n")
    s = build_index(root, tmp_path / "x.db", HashEmbedder(), max_chunks=2)
    assert s.truncated and s.chunks == 2 and s.total_chunks_found > 2
    from repopilot.store import Store

    paths = {r[0] for r in Store(tmp_path / "x.db").db.execute("SELECT path FROM chunks")}
    assert "a.py" in paths
