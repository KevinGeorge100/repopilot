# Decision log (project lead)

| # | Decision | Why | Revisit if |
|---|---|---|---|
| 1 | Product = RepoPilot (cited code Q&A + PR review + MCP server) | Agentic AI is the strongest hiring signal; demoable in 60s | never this week |
| 2 | Scope frozen to the 7-day plan; fix-PR bots, auth, billing, private repos = v2 | One week; finish > sprawl | n/a |
| 3 | Embeddings: local `fastembed` (BAAI/bge-small-en-v1.5, ONNX), behind an `Embedder` interface | No API key or cost, reproducible evals, easy demo deploy | Evals show retrieval is the bottleneck -> try Voyage code model, measured by the eval suite |
| 4 | Store: single SQLite file. FTS5 (BM25) + vector blobs scored with numpy; hybrid ranking via reciprocal rank fusion. NO Postgres/pgvector this week | Zero infra, trivial deploy, repos are small (thousands of chunks) | >100k chunks or concurrent writers |
| 5 | Agent: Anthropic API directly, own small tool-use loop (not a framework); default model claude-sonnet-5-5; prompt caching on the system prompt + tool defs | Fewer moving parts, explainable in interviews | Need sub-agents/MCP client features |
| 6 | Citations are enforced in code: answers must cite path:start-end; a validator checks each citation against the cloned repo; invalid citations count as failures in evals | This is the project's headline quality metric | n/a |
| 7 | Security: https://github.com URLs only, shallow clone, read-only tools, repo text treated as untrusted, per-session cost cap | Prompt injection + abuse + cost | n/a |
| 8 | Planning/process: GSD Core installed project-locally (git-ignored). `ROADMAP.md` + this file are the source of truth; GSD artifacts mirror them | Phase discipline without lock-in | GSD overhead exceeds value |
| 9 | Frontend: Next.js 15 + Tailwind + shadcn/ui; backend FastAPI w/ SSE | Standard, recruiter-legible stack | n/a |
| 10 | Eval metrics: answer accuracy (LLM-judged vs reference), citation validity, p50 latency, $/query | Numbers for the resume | n/a |
| 11 | Retrieval applies a path prior (source 1.0 > docs/examples 0.7 > changelogs 0.4) | Un-weighted hybrid search let docs and changelogs outrank source on `click` queries | Evals show docs-heavy questions suffer |
| 12 | Environment network allowlist extended with Hugging Face model hosts (huggingface.co, cdn-lfs.huggingface.co, cdn-lfs.hf.co, cas-bridge.xethub.hf.co, cas-server.xethub.hf.co, us.aws.cdn.hf.co) | Needed for the one-time fastembed model download | Model is cached/baked into the deploy image |

## Known issues / next tuning
- Indexing click (1.8k chunks) took ~4 min on CPU; batch size and chunk text length need tuning (Day 6 perf pass), or index lazily per repo in the background with a progress bar.
- Test files still rank high for behavioural questions; consider a 0.8 prior for tests/.
| 13 | LLM layer is provider-agnostic. Free-tier default = Gemini (`gemini-3.1-flash-lite`) via its OpenAI-compatible endpoint; Anthropic stays supported (prompt caching only there). Switch with `--provider` or `REPOPILOT_PROVIDER` / `REPOPILOT_MODEL` | Anthropic API needs paid credits; free tiers let the project run at zero cost | Evals show free models fail the citation bar -> evaluate paid models and report both |
| 14 | Gemini key is stored as an environment network credential for generativelanguage.googleapis.com; the proxy injects it. Run locally with `GEMINI_API_KEY=proxy-injected` | Key never appears in chat, code or git | Key rotated or environment changes |
| 15 | Indexing capped at 2,500 chunks per repo (source first, then docs, then changelogs); progress reported in UI | Demo must index in about a minute; embedding runs about 28 chunks/s on CPU | Evals show truncation hurts answers |
| 16 | UI: no component kit; Tailwind + self-hosted fonts (Schibsted Grotesk, Newsreader, JetBrains Mono). Signature element = highlighter on cited lines. Answers show a plain-language verification line | Distinct from templated AI UIs; citations are the product | n/a |
| 17 | search_code results are line-numbered and the prompt demands the narrowest citation range | Without numbers the model cited whole 60-line chunks (useless highlight) | Token cost too high (see below) |

## Free-tier cautions
- Gemini free-tier traffic may be used for training: index public repos only.
- `gemini-3.8-flash` hung (read timeout) in testing; `gemini-3.1-flash-lite` answered in <1s. Re-test other models in the Day 6 evals.
- Gemini 3 needs `thought_signature` echoed back on tool calls (handled via `ToolUse.extra`).
- Thinking tokens count against `max_tokens`; compat client uses 4096.

## Day 4 findings
- Tight citations cost more: one itsdangerous question went from 4.5k to 46k tokens (6 steps vs 2). Day 6: tune k, result truncation and step prompts against the evals.
- Gemini free-tier latency is erratic (same question took 7s, and once over 60s). The UI shows live steps so waiting is visible.
- `npm audit` reports PostCSS issues inside Next 15 (build-time CSS only; fix needs Next 16 major). Accepted for now.
- Throwaway deploy deferred: needs a hosting account. Backend must run on a container host (Render/Railway/Fly), frontend on Vercel; set REPOPILOT_CORS to the frontend origin.
