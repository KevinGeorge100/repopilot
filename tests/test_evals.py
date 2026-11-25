import json
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from repopilot.chunker import chunk_file
from repopilot.cli import app
from repopilot.embed import HashEmbedder
from repopilot.evals.dataset import (
    DatasetError,
    RepoSpec,
    ensure_checkout,
    load_dataset,
    parse_dataset,
    verify_gold,
)
from repopilot.evals.metrics import (
    aggregate,
    percentile,
    repeated_calls,
    score_answer,
    wilson,
)
from repopilot.evals.report import render_markdown
from repopilot.evals.runner import (
    RepoHandle,
    RunConfig,
    read_traces,
    rescore_traces,
    run_eval,
)
from repopilot.llm import LLMResponse, StubLLM, TextBlock, ToolUse, Usage
from repopilot.store import Store

REAL_DATASET = Path(__file__).parent.parent / "evals" / "data" / "questions.json"
SHA = "a" * 40
SRC = "def hello():\n    '''Say hello.'''\n    return 1\n\n\ndef goodbye():\n    return 2\n"


def raw(**overrides):
    base = {
        "version": 1,
        "repos": {"demo": {"url": "https://github.com/acme/demo", "sha": SHA}},
        "questions": [
            {
                "id": "d-01", "repo": "demo", "category": "fact", "question": "What does hello return?",
                "facts": ["return"], "gold": [{"path": "a.py", "start": 1, "end": 3, "anchor": "def hello"}], "negative": False,
            },
            {
                "id": "d-02", "repo": "demo", "category": "negative", "question": "Does demo support YAML configuration files?",
                "facts": ["(not support|does not)"], "gold": [], "negative": True,
            },
        ],
    }
    base.update(overrides)
    return base


# ---- the real dataset ----------------------------------------------------
def test_real_dataset_is_well_formed():
    ds = load_dataset(REAL_DATASET)
    assert len(ds.questions) >= 30
    assert {q.repo for q in ds.questions} == set(ds.repos) and len(ds.repos) >= 3
    assert sum(q.negative for q in ds.questions) >= 5
    assert len({q.id for q in ds.questions}) == len(ds.questions)
    assert all(spec.sha != "" and len(spec.sha) == 40 for spec in ds.repos.values())
    assert {q.category for q in ds.questions} == {"fact", "reasoning", "multi-hop", "negative"}


# ---- validation ----------------------------------------------------------
def test_parse_valid_dataset():
    ds = parse_dataset(raw())
    assert [q.id for q in ds.questions] == ["d-01", "d-02"] and ds.questions[1].negative


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda r: r["repos"]["demo"].update(sha="main"), "sha"),
        (lambda r: r["repos"]["demo"].update(url="https://evil.com/a/b"), "bad url"),
        (lambda r: r["questions"][0].update(repo="nope"), "unknown repo"),
        (lambda r: r["questions"][0].update(facts=["(unclosed"]), "does not compile"),
        (lambda r: r["questions"][0].update(facts=[]), "fact regex"),
        (lambda r: r["questions"][0].update(gold=[]), "needs gold"),
        (lambda r: r["questions"][0]["gold"][0].update(path="../etc/passwd"), "relative"),
        (lambda r: r["questions"][0]["gold"][0].update(start=5, end=2), "invalid"),
        (lambda r: r["questions"][0]["gold"][0].update(anchor=""), "anchor"),
        (lambda r: r["questions"][1].update(id="d-01"), "duplicated"),
        (lambda r: r["questions"][0].update(category="weird"), "category"),
        (lambda r: r["questions"][0].update(question="short"), "too short"),
    ],
)
def test_invalid_datasets_are_rejected_with_a_reason(mutate, message):
    r = raw()
    mutate(r)
    with pytest.raises(DatasetError, match=message):
        parse_dataset(r)


def test_missing_or_broken_file(tmp_path):
    with pytest.raises(DatasetError, match="cannot read"):
        load_dataset(tmp_path / "nope.json")
    (tmp_path / "bad.json").write_text("{not json")
    with pytest.raises(DatasetError, match="cannot read"):
        load_dataset(tmp_path / "bad.json")


# ---- ground-truth verification ------------------------------------------
def test_verify_gold_catches_drift(tmp_path: Path):
    (tmp_path / "a.py").write_text(SRC)
    ds = parse_dataset(raw())
    assert verify_gold(ds, {"demo": tmp_path}) == []
    (tmp_path / "a.py").write_text("x = 1\ny = 2\nz = 3\n" + SRC)  # lines shifted: the anchor is no longer in 1-3
    assert "anchor" in verify_gold(ds, {"demo": tmp_path})[0]
    (tmp_path / "a.py").write_text("x = 1\n")
    assert "past the end" in verify_gold(ds, {"demo": tmp_path})[0]
    (tmp_path / "a.py").unlink()
    assert "does not exist" in verify_gold(ds, {"demo": tmp_path})[0]
    assert "no checkout" in verify_gold(ds, {})[0]


# ---- pinned checkouts ----------------------------------------------------
def test_ensure_checkout_fetches_the_exact_sha(tmp_path: Path):
    calls: list[list[str]] = []

    def fake_run(cmd, cwd=None, **kw):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    ensure_checkout(RepoSpec("demo", "https://github.com/acme/demo", SHA), tmp_path / "demo", fake_run)
    flat = [" ".join(c) for c in calls]
    assert any(c.startswith("git fetch -q --depth 1 -- origin " + SHA) for c in flat)  # "--" guards the refspec
    assert flat[-1] == "git checkout -q --detach FETCH_HEAD"


def test_ensure_checkout_reuses_a_matching_checkout_and_rejects_bad_input(tmp_path: Path):
    (tmp_path / "demo" / ".git").mkdir(parents=True)

    def fake_run(cmd, cwd=None, **kw):
        assert cmd[:3] == ["git", "rev-parse", "HEAD"]
        return subprocess.CompletedProcess(cmd, 0, stdout=SHA + "\n", stderr="")

    spec = RepoSpec("demo", "https://github.com/acme/demo", SHA)
    assert ensure_checkout(spec, tmp_path / "demo", fake_run) == tmp_path / "demo"
    with pytest.raises(DatasetError):
        ensure_checkout(RepoSpec("demo", "https://github.com/acme/demo", "--upload-pack=x"), tmp_path / "x", fake_run)
    with pytest.raises(ValueError):
        ensure_checkout(RepoSpec("demo", "https://evil.com/a/b", SHA), tmp_path / "y", fake_run)


# ---- scoring -------------------------------------------------------------
def payload(answer, valid=(), invalid=(), ungrounded=(), stopped="done", steps=2, tin=100, tout=20):
    return {
        "answer": answer, "stopped": stopped, "steps": steps, "usage": {"input_tokens": tin, "output_tokens": tout, "cache_read_tokens": 0},
        "citations": {"valid": [{"path": p, "start": s, "end": e} for p, s, e in valid], "invalid": list(invalid), "ungrounded": list(ungrounded)},
    }


POS, NEG = parse_dataset(raw()).questions


def test_score_positive_pass_and_each_failure_mode():
    ok = score_answer(POS, payload("hello will return 1", valid=[("a.py", 1, 3)]))
    assert ok.passed and ok.evidence_hit and ok.avg_span == 3
    assert score_answer(POS, payload("hello yields", valid=[("a.py", 1, 3)])).missing_facts == ["return"]
    far = score_answer(POS, payload("it returns", valid=[("a.py", 6, 7)]))  # real lines, wrong place
    assert far.fact_pass and far.evidence_hit is False and not far.passed
    assert not score_answer(POS, payload("it returns", valid=[("b.py", 1, 3)])).passed  # wrong file
    assert not score_answer(POS, payload("it returns")).passed  # no citations at all
    assert not score_answer(POS, payload("it returns", valid=[("a.py", 1, 3)], invalid=[{"citation": "x:1-2", "reason": "r"}])).passed
    assert not score_answer(POS, payload("it returns", valid=[("a.py", 1, 3)], ungrounded=["a.py:1-3"])).passed
    assert not score_answer(POS, payload("it returns", valid=[("a.py", 1, 3)], stopped="budget")).passed


def test_score_negative_questions():
    assert score_answer(NEG, payload("It does not support YAML.")).passed  # no citation needed
    assert score_answer(NEG, payload("It does not support YAML.", valid=[("a.py", 1, 3)])).passed
    assert not score_answer(NEG, payload("Yes, put it in config.yaml.")).passed  # confident fabrication
    bad = score_answer(NEG, payload("It does not support YAML.", invalid=[{"citation": "ghost.py:1-2", "reason": "no file"}]))
    assert not bad.passed  # hedging while citing a file that does not exist still fails
    assert bad.evidence_hit is None


def test_statistics_helpers():
    lo, hi = wilson(30, 38)
    assert 0.63 < lo < 0.65 and 0.88 < hi < 0.92 and wilson(0, 0) == (0.0, 0.0)
    assert wilson(38, 38)[1] == pytest.approx(1.0)
    assert percentile([5, 1, 3, 2, 4], 0.5) == 3 and percentile([1, 2, 3, 4], 0.95) == 4 and percentile([], 0.5) is None


def make_trace(qid, repo, category, negative, passed, latency=2.0, tin=1000, tout=100, valid=1, invalid=0, hit=True, error=None):
    return {
        "id": qid, "repo": repo, "category": category, "negative": negative, "latency_s": latency, "error": error,
        "payload": payload("x", tin=tin, tout=tout, steps=3), "events": [],
        "score": {"passed": passed, "fact_pass": passed, "evidence_hit": None if negative else hit, "citations_ok": invalid == 0,
                  "n_valid": valid, "n_invalid": invalid, "n_ungrounded": 0, "avg_span": 4.0, "missing_facts": [], "reasons": [] if passed else ["why"]},
    }


def test_aggregate_numbers():
    traces = [
        make_trace("a", "r1", "fact", False, True, latency=1.0), make_trace("b", "r1", "fact", False, False, latency=3.0, hit=False, invalid=1),
        make_trace("c", "r2", "negative", True, True, latency=2.0), make_trace("d", "r2", "multi-hop", False, True, latency=10.0),
    ]
    s = aggregate(traces, price_in=1.0, price_out=2.0)
    assert (s["n"], s["passed"], s["pass_rate"]) == (4, 3, 0.75)
    assert s["evidence_hit_rate"] == pytest.approx(2 / 3) and s["negative_pass_rate"] == 1.0
    assert s["citation_validity"] == pytest.approx(4 / 5)  # 4 valid, 1 invalid
    assert s["latency_p50_s"] == 2.0 and s["latency_p95_s"] == 10.0
    assert s["tokens_in_mean"] == 1000 and s["steps_mean"] == 3
    assert s["cost_per_query_usd"] == pytest.approx((1000 * 1.0 + 100 * 2.0) / 1e6)
    assert s["by_repo"]["r1"] == {"n": 2, "passed": 1, "pass_rate": 0.5}
    assert "cost_per_query_usd" not in aggregate(traces)


# ---- the runner ----------------------------------------------------------
@pytest.fixture
def world(tmp_path: Path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "a.py").write_text(SRC)
    emb, db = HashEmbedder(), tmp_path / "idx.db"
    store = Store(db)
    store.add(chunk_file("a.py", SRC), emb)
    store.db.close()
    return parse_dataset(raw()), {"demo": RepoHandle(root, db)}, emb, tmp_path / "out"


def script(answer):
    return [
        LLMResponse([ToolUse("t", "search_code", {"query": "hello"})], "tool_use", Usage(50, 5)),
        LLMResponse([TextBlock(answer)], "end_turn", Usage(60, 10)),
    ]


def good_factory():
    answers = iter(["hello returns 1 (`a.py:1-3`).", "That is not supported: it does not support YAML (see `a.py:1-3`)."])
    return lambda: StubLLM(script(next(answers)))


def test_run_eval_writes_traces_scores_and_events(world):
    ds, handles, emb, out = world
    logs: list[str] = []
    traces = run_eval(ds, handles, emb, good_factory(), RunConfig("t1"), out, log=logs.append, sleep=lambda s: None)
    assert [t["id"] for t in traces] == ["d-01", "d-02"] and all(t["score"]["passed"] for t in traces)
    on_disk = read_traces(out / "traces.jsonl")
    assert len(on_disk) == 2 and on_disk[0]["payload"]["usage"]["input_tokens"] == 110
    kinds = [e["kind"] for e in on_disk[0]["events"]]
    assert kinds == ["tool_call", "tool_result"] and all("t" in e for e in on_disk[0]["events"])
    cfg = json.loads((out / "config.json").read_text())
    assert cfg["config"]["label"] == "t1" and cfg["dataset_version"] == 1
    assert any("PASS" in line for line in logs)


def test_resume_skips_finished_questions(world):
    ds, handles, emb, out = world
    run_eval(ds, handles, emb, good_factory(), RunConfig("t"), out, only={"d-01"}, log=lambda s: None)
    called = []

    def factory():
        called.append(1)
        return StubLLM(script("That is not supported: it does not support YAML (see `a.py:1-3`)."))

    traces = run_eval(ds, handles, emb, factory, RunConfig("t"), out, log=lambda s: None)
    assert len(called) == 1 and len(traces) == 2  # only d-02 ran
    assert len(read_traces(out / "traces.jsonl")) == 2


def test_provider_errors_are_retried_then_recorded_not_raised(world):
    ds, handles, emb, out = world
    state = {"n": 0}

    class Flaky:
        def create(self, *a):
            state["n"] += 1
            raise RuntimeError("LLM provider error 429: slow down")

    sleeps: list[float] = []
    traces = run_eval(ds, handles, emb, lambda: Flaky(), RunConfig("t", retries=2), out, only={"d-01"}, log=lambda s: None, sleep=sleeps.append)
    t = traces[0]
    assert state["n"] == 3 and t["attempts"] == 3 and "429" in t["error"] and not t["score"]["passed"]
    assert t["payload"]["stopped"] == "error" and sleeps == [5, 10]
    s = aggregate(traces)
    assert s["errors"] == 1 and s["latency_p50_s"] is None  # errored runs do not pollute latency


def test_an_outage_stops_the_run_instead_of_burning_every_question(world):
    ds, handles, emb, out = world
    calls = {"n": 0}
    logs: list[str] = []

    class Down:
        def create(self, *a):
            calls["n"] += 1
            raise RuntimeError("LLM provider error 503: high demand")

    traces = run_eval(ds, handles, emb, lambda: Down(), RunConfig("t", retries=0, abort_after=1), out, log=logs.append)
    assert calls["n"] == 1 and len(traces) == 1  # the second question never ran
    assert any("in a row failed on the provider" in m and "resume" in m for m in logs)
    # a healthy question in between resets the counter
    ok_then_down = iter([True, False])
    traces = run_eval(
        ds, handles, emb, lambda: StubLLM(script("hello returns 1 (`a.py:1-3`).")) if next(ok_then_down) else Down(),
        RunConfig("t", retries=0, abort_after=2), out / "b", log=lambda s: None,
    )
    assert len(traces) == 2


def test_retry_wait_is_configurable(world):
    ds, handles, emb, out = world

    class Down:
        def create(self, *a):
            raise RuntimeError("503")

    sleeps: list[float] = []
    run_eval(ds, handles, emb, lambda: Down(), RunConfig("t", retries=2, retry_wait_s=20), out, only={"d-01"}, log=lambda s: None, sleep=sleeps.append)
    assert sleeps == [20, 40]


def test_errored_questions_are_retried_on_resume(world):
    ds, handles, emb, out = world

    class Down:
        def create(self, *a):
            raise RuntimeError("provider down")

    run_eval(ds, handles, emb, lambda: Down(), RunConfig("t", retries=0), out, only={"d-01"}, log=lambda s: None)
    traces = run_eval(ds, handles, emb, good_factory(), RunConfig("t"), out, only={"d-01"}, log=lambda s: None)
    assert traces[0]["error"] is None and traces[0]["score"]["passed"]
    assert len(read_traces(out / "traces.jsonl")) == 1  # the later line replaced the failed one


def test_token_cap_limit_and_fresh(world):
    ds, handles, emb, out = world
    traces = run_eval(ds, handles, emb, good_factory(), RunConfig("t", token_cap=100), out, log=lambda s: None)
    assert len(traces) == 1  # 115 tokens used by the first question, so the cap stops the second
    traces = run_eval(ds, handles, emb, good_factory(), RunConfig("t2"), out / "b", limit=1, log=lambda s: None)
    assert len(traces) == 1
    traces = run_eval(ds, handles, emb, good_factory(), RunConfig("t2"), out / "b", resume=False, log=lambda s: None)
    assert len(traces) == 2


def test_search_k_and_result_cap_reach_the_tool_runner(world):
    ds, handles, emb, out = world

    def tool_result(config: RunConfig, sub: str) -> str:
        seen = {}

        class Spy(StubLLM):
            def create(self, system, messages, tools):
                r = super().create(system, messages, tools)
                if len(self.calls) == 2:
                    seen["result"] = messages[-1]["content"][0]["content"]
                return r

        run_eval(ds, handles, emb, lambda: Spy(script("hello returns 1 (`a.py:1-3`).")), config, out / sub, only={"d-01"}, log=lambda s: None)
        return seen["result"]

    assert tool_result(RunConfig("a", search_k=1), "a").count('"citation"') == 1
    assert tool_result(RunConfig("b", search_k=5), "b").count('"citation"') == 2  # the fixture has two chunks
    capped = tool_result(RunConfig("c", max_result_chars=60), "c")
    assert "[truncated]" in capped and len(capped) < 200


def test_unexpected_exceptions_are_recorded_without_retry_or_crash(world):
    ds, handles, emb, out = world
    calls = {"n": 0}

    def broken():
        calls["n"] += 1
        raise KeyError("boom")

    traces = run_eval(ds, handles, emb, broken, RunConfig("t", retries=3), out, only={"d-01"}, log=lambda s: None, sleep=lambda s: None)
    assert calls["n"] == 1 and traces[0]["error"].startswith("KeyError") and traces[0]["attempts"] == 1


# ---- report --------------------------------------------------------------
def run_dir_with(tmp_path: Path, name: str, traces: list, label: str) -> Path:
    d = tmp_path / name
    d.mkdir()
    (d / "traces.jsonl").write_text("\n".join(json.dumps(t) for t in traces) + "\n")
    (d / "config.json").write_text(json.dumps({"config": {"label": label, "provider": "gemini", "model": "m", "search_k": 8,
                                                          "max_result_chars": 12000, "max_steps": 8}, "index_stats": {"r1": {"chunks": 9, "index_seconds": 3.0}}}))
    return d


def test_report_markdown_and_baseline_comparison(tmp_path: Path):
    before = [make_trace("a", "r1", "fact", False, False, tin=3000, hit=False), make_trace("b", "r1", "fact", False, True, tin=3000)]
    after = [make_trace("a", "r1", "fact", False, True, tin=1000), make_trace("b", "r1", "fact", False, False, tin=1000, hit=False)]
    b_dir, a_dir = run_dir_with(tmp_path, "base", before, "baseline"), run_dir_with(tmp_path, "new", after, "variant")
    result = CliRunner().invoke(app, ["eval", "report", str(a_dir), "--baseline", str(b_dir), "--price-in", "1", "--price-out", "2"])
    assert result.exit_code == 0, result.output
    out = result.output
    assert "# Evaluation: variant" in out and "1/2 = **50%**" in out and "95% CI" in out
    assert "| r1 | 1/2 (50%) |" in out and "Indexing" in out and "Cost per question" in out
    assert "Change from `baseline` to `variant`" in out
    assert "Fixed: a. Regressed: b." in out and "Only 2 of 2 questions changed outcome" in out
    assert "(better)" in out  # tokens dropped from 3000 to 1000
    render_markdown(*[after, {}])  # a run without config.json still renders


def test_report_on_empty_run_fails_cleanly(tmp_path: Path):
    (tmp_path / "empty").mkdir()
    r = CliRunner().invoke(app, ["eval", "report", str(tmp_path / "empty")])
    assert r.exit_code == 1 and "no traces" in r.output


def test_rescore_regrades_stored_answers_without_model_calls(tmp_path: Path):
    ds = parse_dataset(raw())
    stale = {"id": "d-01", "repo": "demo", "category": "fact", "negative": False, "question": "q", "latency_s": 1.0, "error": None,
             "payload": payload("it returns one", valid=[("a.py", 1, 3)]), "events": [],
             "score": {"passed": False, "fact_pass": False, "evidence_hit": True, "citations_ok": True, "n_valid": 1, "n_invalid": 0,
                       "n_ungrounded": 0, "avg_span": 3.0, "missing_facts": ["wrong"], "reasons": ["missing facts: wrong"]}}
    errored = {**stale, "id": "d-02", "error": "provider down"}
    out = rescore_traces(ds, [stale, errored])
    assert out[0]["score"]["passed"] is True  # the old regex was the mistake, the answer was right
    assert out[1] is errored  # failed-on-provider traces are left alone

    run = tmp_path / "run"
    run.mkdir()
    (run / "traces.jsonl").write_text(json.dumps(stale) + "\n")
    (tmp_path / "ds.json").write_text(json.dumps(raw()))
    r = CliRunner().invoke(app, ["eval", "rescore", str(run), "--dataset", str(tmp_path / "ds.json")])
    assert r.exit_code == 0 and "0 passed before, 1 now" in r.output
    assert (run / "traces.original.jsonl").exists()  # the original grading is preserved
    assert read_traces(run / "traces.jsonl")[0]["score"]["passed"] is True
    CliRunner().invoke(app, ["eval", "rescore", str(run), "--dataset", str(tmp_path / "ds.json")])
    assert json.loads((run / "traces.original.jsonl").read_text())["score"]["passed"] is False  # not overwritten twice


# ---- repo preparation ----------------------------------------------------------
def test_prepare_repos_builds_then_reuses_an_index_for_the_same_commit(tmp_path: Path):
    from repopilot.evals.runner import prepare_repos

    ds = parse_dataset(raw())
    work = tmp_path / "work"
    (work / "repos" / "demo" / ".git").mkdir(parents=True)
    (work / "repos" / "demo" / "a.py").write_text(SRC)

    def fake_run(cmd, cwd=None, **kw):  # the checkout already matches the pinned sha
        return subprocess.CompletedProcess(cmd, 0, stdout=SHA + "\n", stderr="")

    logs: list[str] = []
    handles, stats = prepare_repos(ds, work, HashEmbedder(), logs.append, run=fake_run)
    assert stats["demo"]["chunks"] >= 2 and handles["demo"].db.exists()
    assert any("indexing" in m for m in logs)

    logs.clear()
    prepare_repos(ds, work, HashEmbedder(), logs.append, run=fake_run)
    assert any("reusing index" in m for m in logs)  # same sha, same index version: no re-embedding



def test_repeated_and_unfinished_runs_are_measured_from_the_events():
    ev = lambda name, **inp: {"kind": "tool_call", "name": name, "input": inp}
    thrash = make_trace("a", "r", "fact", False, False)
    thrash["events"] = [ev("search_code", query="def prompt("), ev("search_code", query="def prompt"), ev("search_code", query="Prompt, DEF!"),
                        ev("read_file", path="x.py"), ev("read_file", path="x.py"), ev("read_file", path="y.py"), {"kind": "tool_result"}]
    thrash["payload"]["stopped"] = "max_steps"
    clean = make_trace("b", "r", "fact", False, True)
    clean["events"] = [ev("search_code", query="alpha"), ev("search_code", query="beta")]
    assert repeated_calls(thrash) == 3 and repeated_calls(clean) == 0
    s = aggregate([thrash, clean])
    assert (s["unfinished"], s["repeated_calls"], s["questions_with_repeats"]) == (1, 3, 1)
    md = render_markdown([thrash, clean], {"config": {"label": "x"}})
    assert "no finished answer | 1 of 2" in md and "Repeated tool calls | 3 (in 1 questions)" in md


def test_comparison_leaves_out_questions_a_provider_error_prevented(tmp_path: Path):
    before = [make_trace("a", "r1", "fact", False, True), make_trace("b", "r1", "fact", False, False), make_trace("c", "r1", "fact", False, True)]
    after = [make_trace("a", "r1", "fact", False, True), make_trace("b", "r1", "fact", False, True),
             make_trace("c", "r1", "fact", False, False, error="LLM provider error 429: quota")]
    b_dir, a_dir = run_dir_with(tmp_path, "base", before, "baseline"), run_dir_with(tmp_path, "new", after, "variant")
    out = CliRunner().invoke(app, ["eval", "report", str(a_dir), "--baseline", str(b_dir)]).output
    assert "Compared on the 2 questions both runs answered; the other 1 hit a provider error" in out
    assert "Provider errors (not counted against the agent below) | 1" in out
    assert "Passed among the 2 answered questions | 2/2 = 100%" in out
    assert "Fixed: b. Regressed: none." in out  # c is excluded, not counted as a regression
    assert "| Questions passed | 50% | 100% |" in out  # 1/2 before, 2/2 after, on the same two questions
