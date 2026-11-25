# RepoPilot 7-day roadmap
- [x] Day 1: scaffold, CLAUDE.md, CI, ingest, tree-sitter chunker (tests)
- [x] Day 2: local embeddings, SQLite hybrid store (FTS5 + vectors + RRF), search_code/read_file/list_tree tools, `index`/`search` CLI (19 tests)
- [x] Day 3: agent loop, citation validator + repair turn, token budget, `ask` CLI, multi-provider LLM (Anthropic, Gemini, Groq, OpenRouter). Live-verified on click via Gemini free tier (38 tests)
- [x] Day 4: FastAPI (background indexing, SSE streaming, rate limits, citation file viewer) + Next.js UI (evidence panel with highlighted cited lines, mobile slide-over). Verified in a real browser. Throwaway deploy NOT done: no hosting account attached; Dockerfile + CI ready
- [ ] Day 5: PR review mode + MCP server
- [ ] Day 6: eval suite (30-50 Q&A), tracing, one measured improvement
- [ ] Day 7: deploy, rate limits/cost caps, README + diagram, demo video

## v2 (out of scope this week)
Auto fix PRs, auth/billing, multi-repo, private repos.
