import os
from pathlib import Path

import typer

from .agent import Agent
from .diff import fetch_pr_diff, parse_diff, parse_pr_url
from .embed import FastEmbedder
from .ingest import chunk_repo, clone
from .llm import make_llm
from .review import PRReviewer
from .store import Store
from .toolbox import ToolRunner
from .tools import search_code

app = typer.Typer(help="RepoPilot: cited code intelligence for any GitHub repo.")
eval_app = typer.Typer(help="Run and report the evaluation suite (see evals/).")
app.add_typer(eval_app, name="eval")
WORKDIR = Path(".repopilot")
EVAL_DATASET = Path("evals/data/questions.json")
EVAL_WORKDIR = Path(".repopilot-eval")
EVAL_RESULTS = Path("evals/results")


def _name(url: str) -> str:
    return url.rstrip("/").split("/")[-1].removesuffix(".git")


@app.callback()
def main() -> None:
    """RepoPilot CLI."""


@app.command()
def ingest(url: str, workdir: Path = WORKDIR) -> None:
    """Clone a repo and report how it was chunked."""
    dest = workdir / "repos" / _name(url)
    dest.parent.mkdir(parents=True, exist_ok=True)
    clone(url, dest)
    chunks = chunk_repo(dest)
    defs = sum(c.kind == "definition" for c in chunks)
    typer.echo(f"{len(chunks)} chunks ({defs} definition-level) from {dest}")


@app.command()
def index(url: str, workdir: Path = WORKDIR) -> None:
    """Clone, chunk, embed and store a repo (rebuilds the index)."""
    name = _name(url)
    dest = workdir / "repos" / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    clone(url, dest)
    chunks = chunk_repo(dest)
    db = workdir / "index" / f"{name}.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    db.unlink(missing_ok=True)
    store = Store(db)
    store.add(chunks, FastEmbedder())
    typer.echo(f"indexed {store.count()} chunks -> {db}")


@app.command()
def search(name: str, query: str, k: int = 5, workdir: Path = WORKDIR) -> None:
    """Hybrid search an indexed repo; prints citations."""
    store = Store(workdir / "index" / f"{name}.db")
    for h in search_code(store, FastEmbedder(), query, k):
        first = h["text"].strip().splitlines()[0][:90]
        typer.echo(f"{h['citation']:<45} {h['score']:.4f}  {first}")


@app.command()
def ask(
    name: str, question: str, provider: str | None = None, model: str | None = None, verbose: bool = False, workdir: Path = WORKDIR
) -> None:
    """Ask a cited question about an indexed repo. Provider: anthropic|gemini|groq|openrouter."""
    try:
        llm = make_llm(provider, model)
    except RuntimeError as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(1) from e
    agent = Agent(llm, Store(workdir / "index" / f"{name}.db"), FastEmbedder(), workdir / "repos" / name)
    try:
        _run(agent, question, verbose)
    except RuntimeError as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(1) from e


def _run(agent: Agent, question: str, verbose: bool) -> None:
    for ev in agent.stream(question):
        if ev.kind == "tool_call" and verbose:
            typer.echo(f"  -> {ev.data['name']}({ev.data['input']})", err=True)
        elif ev.kind == "repair":
            typer.echo("  (citation check failed; asking the model to fix)", err=True)
        elif ev.kind == "answer":
            r = ev.data["result"]
            typer.echo(r.answer)
            c = r.citations
            typer.echo(
                f"\n[{r.stopped}] steps={r.steps} tokens in/out={r.usage.input_tokens}/{r.usage.output_tokens} "
                f"cache_read={r.usage.cache_read_tokens} citations ok={len(c.cited)} invalid={len(c.invalid)} ungrounded={len(c.ungrounded)}",
                err=True,
            )


@app.command()
def review(url: str, provider: str | None = None, model: str | None = None, workdir: Path = WORKDIR) -> None:
    """Review a public GitHub pull request. If its repo is indexed, the reviewer can look up code."""
    try:
        owner, name, number = parse_pr_url(url)
        llm = make_llm(provider, model)
        pd = parse_diff(fetch_pr_diff(owner, name, number))
    except (ValueError, RuntimeError) as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(1) from e
    rid = f"{owner}--{name}"
    db = workdir / "index" / f"{rid}.db"
    tools = ToolRunner(Store(db), FastEmbedder(), workdir / "repos" / rid) if db.exists() else None
    try:
        result = PRReviewer(llm, pd, tools).run(f"{owner}/{name}#{number}")
    except RuntimeError as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(1) from e
    typer.echo(result.summary + "\n")
    for f in result.findings:
        typer.echo(f"[{f.severity}] {f.path}:{f.start_line}-{f.end_line}  {f.title}\n  {f.explanation}")
        if f.suggestion:
            typer.echo(f"  Fix: {f.suggestion}")
        typer.echo("")
    if not result.findings:
        typer.echo("No problems found.")
    for r in result.rejected:
        typer.echo(f"(dropped: {r['title']}: {r['reason']})", err=True)
    typer.echo(
        f"[{result.stopped}] files={len(pd.files)} steps={result.steps} tokens in/out="
        f"{result.usage.input_tokens}/{result.usage.output_tokens} repo_context={'yes' if tools else 'no'}",
        err=True,
    )


@app.command()
def mcp(workdir: Path = WORKDIR) -> None:
    """Run the MCP server over stdio (for Claude Code, Claude Desktop and other MCP clients)."""
    from .mcp_server import build_server

    build_server(workdir).run("stdio")


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Run the API server (SSE streaming)."""
    import logging

    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

    uvicorn.run("repopilot.server:app_factory", factory=True, host=host, port=port)


def _load_eval_dataset(path: Path):
    from .evals.dataset import DatasetError, load_dataset

    try:
        return load_dataset(path)
    except DatasetError as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(1) from e


@eval_app.command("verify")
def eval_verify(dataset: Path = EVAL_DATASET, workdir: Path = EVAL_WORKDIR) -> None:
    """Check out each repo at its pinned commit and verify every gold range and anchor."""
    from .evals.dataset import ensure_checkout, verify_gold

    ds = _load_eval_dataset(dataset)
    roots = {n: ensure_checkout(spec, workdir / "repos" / n) for n, spec in ds.repos.items()}
    problems = verify_gold(ds, roots)
    for p in problems:
        typer.echo(f"PROBLEM {p}", err=True)
    gold = sum(len(q.gold) for q in ds.questions)
    typer.echo(f"{len(ds.questions)} questions, {gold} gold ranges, {len(problems)} problems")
    if problems:
        raise typer.Exit(1)


@eval_app.command("prepare")
def eval_prepare(dataset: Path = EVAL_DATASET, workdir: Path = EVAL_WORKDIR, force: bool = False) -> None:
    """Check out and index every eval repo (reuses an index built for the same commit)."""
    from .evals.runner import prepare_repos

    prepare_repos(_load_eval_dataset(dataset), workdir, FastEmbedder(), typer.echo, force)


@eval_app.command("run")
def eval_run(
    label: str,
    dataset: Path = EVAL_DATASET,
    workdir: Path = EVAL_WORKDIR,
    provider: str | None = None,
    model: str | None = None,
    k: int = 8,
    max_chars: int = 12_000,
    max_steps: int = 8,
    min_interval: float = 0.0,
    token_cap: int | None = None,
    retries: int = 1,
    retry_wait: float = 5.0,
    abort_after: int = 5,
    only: str | None = None,
    limit: int | None = None,
    fresh: bool = False,
    out: Path | None = None,
) -> None:
    """Run every question through the agent and write traces to evals/results/<label>/."""
    from .evals.runner import RunConfig, prepare_repos, run_eval

    ds = _load_eval_dataset(dataset)
    try:
        probe = make_llm(provider, model)  # fail fast on a missing key
    except RuntimeError as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(1) from e
    # Record what actually ran, not "default", so a report is reproducible.
    eff_provider = (provider or os.environ.get("REPOPILOT_PROVIDER") or "anthropic").lower()
    eff_model = getattr(probe, "model", None) or model
    embedder = FastEmbedder()
    handles, stats = prepare_repos(ds, workdir, embedder, typer.echo)
    cfg = RunConfig(
        label, eff_provider, eff_model, k, max_chars, max_steps,
        retries=retries, retry_wait_s=retry_wait, abort_after=abort_after, min_interval_s=min_interval, token_cap=token_cap,
    )
    run_dir = out or EVAL_RESULTS / label
    traces = run_eval(
        ds, handles, embedder, lambda: make_llm(provider, model), cfg, run_dir,
        index_stats=stats, resume=not fresh, only=set(only.split(",")) if only else None, limit=limit, log=typer.echo,
    )
    passed = sum(t["score"]["passed"] for t in traces)
    typer.echo(f"\n{passed}/{len(traces)} passed. Traces in {run_dir}. Next: repopilot eval report {run_dir}")


@eval_app.command("retrieval")
def eval_retrieval(
    dataset: Path = EVAL_DATASET,
    workdir: Path = EVAL_WORKDIR,
    symbols: bool = True,
    embed_chars: int | None = None,
    queries_from: Path | None = None,
) -> None:
    """Measure where the gold evidence ranks in search results. No model calls.

    --queries-from RUN_DIR replays the searches that run's agent actually issued instead of the question text.

    --no-symbols turns name matching off on the same index. --embed-chars N builds a separate index that embeds
    only the first N characters of each chunk (stored beside the main one) to compare accuracy against speed.
    """
    import time

    from .evals.retrieval import evaluate_retrieval, summarize
    from .evals.runner import RepoHandle, prepare_repos
    from .pipeline import build_index

    ds = _load_eval_dataset(dataset)
    embedder = FastEmbedder()
    handles, _ = prepare_repos(ds, workdir, embedder, typer.echo)
    if embed_chars is not None:
        alt: dict[str, RepoHandle] = {}
        for name, h in handles.items():
            db = workdir / "index" / f"{name}.e{embed_chars}.db"
            t0 = time.monotonic()
            if not db.exists():
                build_index(h.root, db, embedder, embed_chars=embed_chars)
                typer.echo(f"  {name}: built {embed_chars}-char index in {time.monotonic() - t0:.0f}s")
            alt[name] = RepoHandle(h.root, db)
        handles = alt
    if queries_from:
        from .evals.retrieval import evaluate_queries
        from .evals.runner import read_traces

        past = read_traces(queries_from / "traces.jsonl")
        s = summarize(evaluate_queries(ds, handles, embedder, past, symbols))
        source = f", replaying the queries of {queries_from.name}"
    else:
        s = summarize(evaluate_retrieval(ds, handles, embedder, symbols))
        source = ", question text as the query"
    pct = lambda x: "n/a" if x is None else f"{x * 100:.0f}%"
    label = f"symbols {'on' if symbols else 'off'}, embed {embed_chars or 'default'} chars{source}"
    typer.echo(
        f"retrieval ({label}): {s['n']} positive questions | hit@1 {pct(s['hit@1'])}  hit@3 {pct(s['hit@3'])}  "
        f"hit@8 {pct(s['hit@8'])}  hit@20 {pct(s['hit@20'])}  MRR {s['mrr']:.3f}"
    )
    if s["missed"]:
        typer.echo(f"  not in the top 20: {', '.join(s['missed'])}")


@eval_app.command("rescore")
def eval_rescore(run_dir: Path, dataset: Path = EVAL_DATASET) -> None:
    """Re-grade a finished run against the current dataset (no model calls). The original traces are kept."""
    import json
    import shutil

    from .evals.runner import read_traces, rescore_traces

    ds = _load_eval_dataset(dataset)
    traces_path = run_dir / "traces.jsonl"
    traces = read_traces(traces_path)
    if not traces:
        typer.echo(f"error: no traces in {run_dir}", err=True)
        raise typer.Exit(1)
    backup = run_dir / "traces.original.jsonl"
    if not backup.exists():
        shutil.copyfile(traces_path, backup)
    before = sum(t["score"]["passed"] for t in traces)
    rescored = rescore_traces(ds, traces)
    traces_path.write_text("".join(json.dumps(t, ensure_ascii=False) + "\n" for t in rescored))
    cfg_path = run_dir / "config.json"
    if cfg_path.exists():
        cfg = json.loads(cfg_path.read_text())
        cfg["dataset_version"] = ds.version
        cfg["rescored"] = True
        cfg_path.write_text(json.dumps(cfg, indent=1))
    after = sum(t["score"]["passed"] for t in rescored)
    typer.echo(f"re-scored {len(rescored)} questions against dataset v{ds.version}: {before} passed before, {after} now")


@eval_app.command("report")
def eval_report(
    run_dir: Path,
    baseline: Path | None = None,
    price_in: float | None = None,
    price_out: float | None = None,
    write: Path | None = None,
) -> None:
    """Render a run as markdown. Prices are dollars per million tokens (optional). --baseline adds a comparison."""
    from .evals.report import load_run, render_markdown

    traces, cfg = load_run(run_dir)
    if not traces:
        typer.echo(f"error: no traces in {run_dir}", err=True)
        raise typer.Exit(1)
    md = render_markdown(traces, cfg, price_in, price_out, load_run(baseline) if baseline else None)
    if write:
        write.parent.mkdir(parents=True, exist_ok=True)
        write.write_text(md)
        typer.echo(f"wrote {write}")
    else:
        typer.echo(md)


if __name__ == "__main__":
    app()
