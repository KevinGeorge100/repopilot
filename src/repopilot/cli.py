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
WORKDIR = Path(".repopilot")


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
def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Run the API server (SSE streaming)."""
    import logging

    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

    uvicorn.run("repopilot.server:app_factory", factory=True, host=host, port=port)


if __name__ == "__main__":
    app()
