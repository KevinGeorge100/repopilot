# RepoPilot

Ask a public GitHub repo anything. Every answer cites exact lines of code, and RepoPilot checks that each
citation is real and that the agent actually read it.

## How it works
1. **Index:** shallow-clone the repo, split source into functions/classes with tree-sitter, embed locally
   (`bge-small`), store in one SQLite file (FTS5 keyword search + vectors, fused by reciprocal rank).
2. **Ask:** a small tool-use agent (`search_code`, `read_file`, `list_tree`) streams its steps over SSE.
3. **Verify:** every `path:start-end` citation is checked against the repo and against what the agent retrieved.
   A failed check triggers one repair turn; anything still wrong is shown struck through in the UI.

Providers: Gemini (free tier), Groq, OpenRouter, Anthropic. See `DECISIONS.md` for the reasoning.

## Run it
```bash
cp .env.example .env            # add a free key from aistudio.google.com/api-keys
uv sync
export GEMINI_API_KEY=... REPOPILOT_PROVIDER=gemini
uv run repopilot serve          # API on :8000

cd web && npm install && npm run dev   # UI on :3000
```
CLI: `uv run repopilot index <github-url>` then `uv run repopilot ask <owner--repo> "question"`.

## Safety
Public GitHub URLs only, shallow clones, read-only tools, repo text treated as untrusted data, per-IP rate
limits, step and token budgets, chunk cap per repo. Code snippets are sent to the LLM provider: do not index
private code.

## Status
See `ROADMAP.md`. Tests: `uv run pytest` (49), `cd web && npm run lint && npm run build`.

## License
MIT. See `LICENSE`.
