# RepoPilot 7-day roadmap
- [x] Day 1: scaffold, CLAUDE.md, CI, ingest, tree-sitter chunker (tests)
- [x] Day 2: local embeddings, SQLite hybrid store (FTS5 + vectors + RRF), search_code/read_file/list_tree tools, `index`/`search` CLI (19 tests)
- [x] Day 3: agent loop, citation validator + repair turn, token budget, `ask` CLI, multi-provider LLM (Anthropic, Gemini, Groq, OpenRouter). Live-verified on click via Gemini free tier (38 tests)
- [x] Day 4: FastAPI (background indexing, SSE streaming, rate limits, citation file viewer) + Next.js UI (evidence panel with highlighted cited lines, mobile slide-over). Verified in a real browser. Throwaway deploy NOT done: no hosting account attached; Dockerfile + CI ready
- [x] Day 5: PR review (diff parser, reviewer whose findings must anchor to added lines, API + CLI) and MCP server (7 tools, stdio). 103 tests. Review UI deferred (needs a diff view)
- [x] Day 6: eval harness (38 verified questions on pinned repos, deterministic scoring, traces, reports, no-model retrieval eval) and a measured improvement iteration: no-answer questions 3 to 0, repeated searches 19 to 4, tokens per question -39%, index build -30%. Caveats: one run per variant, 2 questions unanswered (free-tier daily quota), final index not re-run end to end
- [~] Day 7: deploy-ready (one Render service serving UI and API, demo repos indexed at build time, cached real examples, daily cap, Dockerfile simulated, DEPLOY.md, README rewritten). Remaining: create the Render service and add the live link

## v2 (out of scope this week)
Auto fix PRs, auth/billing, multi-repo, private repos.
