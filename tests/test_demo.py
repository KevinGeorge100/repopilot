import json
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from repopilot.demo import (
    AnswerCache,
    DemoRepo,
    export_answers,
    load_manifest,
    normalize_question,
    seed_demo,
)
from repopilot.embed import HashEmbedder
from repopilot.evals.dataset import parse_dataset
from repopilot.llm import LLMResponse, StubLLM, TextBlock, ToolUse, Usage
from repopilot.pipeline import build_index
from repopilot.server import DailyCap, cached_events, create_app

ROOT = Path(__file__).parent.parent
SHA = "a" * 40
SRC = "def hello():\n    '''Say hello.'''\n    return 1\n"
URL = "https://github.com/acme/demo"
REPO = DemoRepo("acme--demo", "acme/demo", URL, SHA, "A demo repo.")


def entry(question="What does hello return?", answer="It returns 1 (`a.py:1-3`)."):
    payload = {"answer": answer, "stopped": "done", "steps": 2,
               "usage": {"input_tokens": 10, "output_tokens": 2, "cache_read_tokens": 0},
               "citations": {"valid": [{"path": "a.py", "start": 1, "end": 3}], "invalid": [], "ungrounded": [], "validity": 1.0, "ok": True}}
    events = [{"t": 0.4, "kind": "tool_call", "name": "search_code", "input": {"query": "hello"}},
              {"t": 0.5, "kind": "tool_result", "name": "search_code", "error": False, "chars": 90}]
    return {"repo": "acme--demo", "question": question, "events": events, "payload": payload, "source": {"run": "r1", "model": "m"}}


# ---- manifest and cache --------------------------------------------------------
def test_real_manifest_and_cached_answers_are_consistent():
    repos = load_manifest(ROOT / "demo" / "manifest.json")
    assert [r.id for r in repos] == ["pallets--itsdangerous", "pallets--click", "sindresorhus--slugify"]
    assert all(len(r.sha) == 40 and r.description for r in repos)
    answers = json.loads((ROOT / "demo" / "answers.json").read_text())["answers"]
    ids = {r.id for r in repos}
    assert len(answers) >= 12 and {a["repo"] for a in answers} == ids
    for a in answers:
        p = a["payload"]
        assert p["stopped"] == "done" and p["answer"].strip() and p["citations"]["ok"] and not p["citations"]["invalid"]
        assert a["source"]["model"] and a["question"].strip()
        assert all(1 <= c["start"] <= c["end"] for c in p["citations"]["valid"])
    assert (ROOT / "demo" / "answers.json").stat().st_size < 200_000
    # every cached question really is an evaluation question, so each answer was scored
    qs = {q["question"] for q in json.loads((ROOT / "evals" / "data" / "questions.json").read_text())["questions"]}
    assert {a["question"] for a in answers} <= qs


@pytest.mark.parametrize("bad", [{"url": "https://evil.com/a/b", "sha": SHA}, {"url": URL, "sha": "main"}])
def test_manifest_rejects_bad_entries(tmp_path: Path, bad):
    (tmp_path / "m.json").write_text(json.dumps({"repos": [bad]}))
    with pytest.raises(ValueError):
        load_manifest(tmp_path / "m.json")


def test_answer_cache_ignores_case_and_punctuation_and_keeps_order():
    cache = AnswerCache([entry(), entry("Second question here?")])
    assert cache.get("acme--demo", "WHAT does hello   return") is not None
    assert cache.get("acme--demo", "what does hello return?!") is not None
    assert cache.get("acme--demo", "what does goodbye return") is None
    assert cache.get("other--repo", "what does hello return") is None
    assert cache.examples("acme--demo") == ["What does hello return?", "Second question here?"] and len(cache) == 2
    assert normalize_question("  Hi,   THERE! ") == "hi there"
    assert len(AnswerCache.load(Path("/nonexistent/answers.json"))) == 0


# ---- exporting real answers ----------------------------------------------------
def make_ds():
    qs = [{"id": f"d-{i:02d}", "repo": "demo", "category": cat, "question": f"Question number {i} about demo?", "facts": ["x"],
           "gold": [] if cat == "negative" else [{"path": "a.py", "start": 1, "end": 2, "anchor": "def"}], "negative": cat == "negative"}
          for i, cat in enumerate(["fact", "fact", "reasoning", "multi-hop", "negative", "negative", "fact"])]
    return parse_dataset({"version": 1, "repos": {"demo": {"url": URL, "sha": SHA}}, "questions": qs})


def trace(qid, cat, passed=True, error=None, stopped="done", answer="An answer.", ok=True):
    return {"id": qid, "repo": "demo", "category": cat, "error": error, "events": [{"kind": "tool_call", "name": "x", "input": {}}],
            "score": {"passed": passed}, "payload": {"answer": answer, "stopped": stopped, "citations": {"ok": ok, "valid": []}}}


def test_export_picks_only_good_answers_spreads_types_and_caps_negatives():
    ds = make_ds()
    traces = [trace("d-00", "fact"), trace("d-01", "fact", passed=False), trace("d-02", "reasoning"), trace("d-03", "multi-hop", error="boom"),
              trace("d-04", "negative"), trace("d-05", "negative"), trace("d-06", "fact", stopped="max_steps")]
    out = export_answers(ds, traces, [REPO], per_repo=6, source={"run": "r"})
    qs = [e["question"] for e in out]
    assert qs == ["Question number 0 about demo?", "Question number 2 about demo?", "Question number 4 about demo?"]  # fact, reasoning, one negative
    assert all(e["repo"] == "acme--demo" and e["source"] == {"run": "r"} for e in out)
    assert out[0]["payload"] is traces[0]["payload"]  # copied verbatim, never edited
    assert [e["question"] for e in export_answers(ds, traces, [REPO], per_repo=1)] == ["Question number 0 about demo?"]
    skipped = export_answers(ds, traces, [REPO], exclude={"d-04"})
    assert "Question number 4 about demo?" not in [e["question"] for e in skipped]
    assert [e["question"] for e in skipped][-1] == "Question number 5 about demo?"  # the other negative steps in
    assert export_answers(ds, traces, [DemoRepo("x--y", "x/y", "https://github.com/x/y", SHA, "")]) == []  # repo not in the manifest


# ---- seeding -------------------------------------------------------------------
def test_seed_builds_an_index_strips_git_and_is_idempotent(tmp_path: Path):
    work = tmp_path / "w"
    (work / "repos" / REPO.id / ".git").mkdir(parents=True)
    (work / "repos" / REPO.id / "a.py").write_text(SRC)

    def fake_run(cmd, cwd=None, **kw):  # the checkout already matches the pinned sha
        return subprocess.CompletedProcess(cmd, 0, stdout=SHA + "\n", stderr="")

    logs: list[str] = []
    out = seed_demo([REPO], work, HashEmbedder(), logs.append, run=fake_run)
    assert out[REPO.id]["chunks"] >= 1 and (work / "index" / f"{REPO.id}.db").exists()
    assert not (work / "repos" / REPO.id / ".git").exists() and (work / "repos" / REPO.id / "a.py").exists()
    again = seed_demo([REPO], work, HashEmbedder(), logs.append, run=fake_run)
    assert again == {} and any("already seeded" in m for m in logs)


# ---- the server in demo mode ---------------------------------------------------
@pytest.fixture
def world(tmp_path: Path):
    work, demo = tmp_path / "work", tmp_path / "demo"
    (work / "repos" / REPO.id).mkdir(parents=True)
    (work / "repos" / REPO.id / "a.py").write_text(SRC)
    build_index(work / "repos" / REPO.id, work / "index" / f"{REPO.id}.db", HashEmbedder())
    demo.mkdir()
    (demo / "manifest.json").write_text(json.dumps({"repos": [{"url": URL, "sha": SHA, "description": REPO.description}]}))
    (demo / "answers.json").write_text(json.dumps({"answers": [entry()]}))
    return work, demo


def live_llm():
    return StubLLM([LLMResponse([ToolUse("t", "search_code", {"query": "hello"})], "tool_use", Usage(5, 1)),
                    LLMResponse([TextBlock("hello returns 1 (`a.py:1-3`).")], "end_turn", Usage(5, 3))])


def make_app(world, llm_factory=live_llm, **kw):
    work, demo = world
    return TestClient(create_app(work, llm_factory, HashEmbedder(), lambda u, d: d, demo_dir=demo, demo_mode=True, **kw))


def parse_sse(text: str):
    out = []
    for block in text.strip().split("\n\n"):
        ev, data = block.split("\n", 1)
        out.append((ev.removeprefix("event: "), json.loads(data.removeprefix("data: "))))
    return out


def test_config_lists_seeded_repos_with_examples_and_limits(world):
    cfg = make_app(world).get("/api/config").json()
    assert cfg["demo"] is True and cfg["indexing"] is False and cfg["live_questions"] is True and cfg["daily_remaining"] == 150
    assert cfg["repos"] == [{"id": "acme--demo", "name": "acme/demo", "description": "A demo repo.", "chunks": cfg["repos"][0]["chunks"],
                             "examples": ["What does hello return?"]}] and cfg["repos"][0]["chunks"] >= 1

    def no_key():
        raise RuntimeError("GEMINI_API_KEY is not set")

    assert make_app(world, no_key).get("/api/config").json()["live_questions"] is False  # the UI can say so


def test_demo_mode_refuses_new_repos_but_reports_existing_ones(world):
    c = make_app(world)
    assert c.post("/api/repos", json={"url": URL}).json()["status"] == "ready"
    r = c.post("/api/repos", json={"url": "https://github.com/someone/else"})
    assert r.status_code == 403 and "pre-indexed" in r.json()["detail"]


def test_cached_answers_replay_instantly_without_touching_the_model(world):
    def never():
        raise AssertionError("the model must not be called for a cached answer")

    c = make_app(world, never)
    events = parse_sse(c.post("/api/ask", json={"repo": "acme--demo", "question": "what DOES hello return"}).text)
    assert [k for k, _ in events] == ["tool_call", "tool_result", "answer"]
    assert "t" not in events[0][1] and "kind" not in events[0][1]  # event metadata stripped like a live stream
    answer = events[-1][1]
    assert answer["cached"] is True and answer["source"] == {"run": "r1", "model": "m"} and answer["citations"]["ok"]
    assert [k for k, _ in parse_sse("".join(cached_events(entry())))] == ["tool_call", "tool_result", "answer"]


def test_live_questions_spend_the_daily_cap_and_cached_ones_do_not(world):
    c = make_app(world, daily_cap=1)
    live = {"repo": "acme--demo", "question": "Something not in the cache at all?"}
    first = parse_sse(c.post("/api/ask", json=live).text)
    assert first[-1][0] == "answer" and first[-1][1].get("cached") is None
    assert c.get("/api/config").json()["daily_remaining"] == 0
    blocked = c.post("/api/ask", json={**live, "question": "Another question not cached?"})
    assert blocked.status_code == 429 and "example questions still work" in blocked.json()["detail"]
    cached = c.post("/api/ask", json={"repo": "acme--demo", "question": "What does hello return?"})
    assert cached.status_code == 200 and parse_sse(cached.text)[-1][1]["cached"] is True


def test_daily_cap_resets_each_utc_day():
    day = ["2026-11-26"]
    cap = DailyCap(2, today=lambda: day[0])
    assert cap.allow() and cap.allow() and not cap.allow() and cap.remaining == 0
    day[0] = "2026-11-27"
    assert cap.remaining == 2 and cap.allow()


def test_the_web_ui_is_served_from_the_same_origin_and_api_routes_win(world, tmp_path: Path):
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<html><body>RepoPilot UI</body></html>")
    (web / "app.js").write_text("console.log(1)")
    c = make_app(world, static_dir=web)
    assert "RepoPilot UI" in c.get("/").text and c.get("/app.js").status_code == 200
    assert c.get("/api/health").json() == {"ok": True}  # the API is not shadowed by the static mount
    assert c.get("/api/nope").status_code == 404 and c.get("/missing.html").status_code == 404
    assert make_app(world).get("/").status_code == 404  # no static dir configured: API only
