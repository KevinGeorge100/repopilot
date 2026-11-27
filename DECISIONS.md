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
| 13 | LLM layer is provider-agnostic. Free-tier default = Gemini (`gemini-3.5-flash-lite`, see #29) via its OpenAI-compatible endpoint; Anthropic stays supported (prompt caching only there). Switch with `--provider` or `REPOPILOT_PROVIDER` / `REPOPILOT_MODEL` | Anthropic API needs paid credits; free tiers let the project run at zero cost | Evals show free models fail the citation bar -> evaluate paid models and report both |
| 14 | Gemini key is stored as an environment network credential for generativelanguage.googleapis.com; the proxy injects it. Run locally with `GEMINI_API_KEY=proxy-injected` | Key never appears in chat, code or git | Key rotated or environment changes |
| 15 | Indexing capped at 2,500 chunks per repo (source first, then docs, then changelogs); progress reported in UI | Demo must index in about a minute; embedding runs about 28 chunks/s on CPU | Evals show truncation hurts answers |
| 16 | UI: no component kit; Tailwind + self-hosted fonts (Schibsted Grotesk, Newsreader, JetBrains Mono). Signature element = highlighter on cited lines. Answers show a plain-language verification line | Distinct from templated AI UIs; citations are the product | n/a |
| 17 | search_code results are line-numbered and the prompt demands the narrowest citation range | Without numbers the model cited whole 60-line chunks (useless highlight) | Token cost too high (see below) |
| 18 | PR review returns findings through a terminal `submit_review` tool (portable across providers). Each finding is validated: path is in the diff, range is at most 40 lines, and it overlaps a line the PR ADDED. Rejections trigger one repair turn; unanchored findings are never shown | Same principle as citations: do not show what cannot be verified | Evals show valid findings are being rejected |
| 19 | PR diffs come from the GitHub REST API (`Accept: application/vnd.github.diff`), not `github.com/<pr>.diff`; optional `GITHUB_TOKEN`; public PRs only; 1.5 MB cap | The `.diff` URL redirects to a second host (blocked in our sandbox, and a fragile dependency); the API is documented | API rate limits bite (60/hour unauthenticated) |
| 20 | Repo tools are optional in review: if the repo is indexed the reviewer can search the default branch, otherwise it reviews the diff alone | Reviews must work on any public PR without waiting for an index | Reviews miss cross-file bugs often |
| 21 | MCP server is local stdio on the official SDK (v2: `MCPServer`, not `FastMCP`). Seven tools; the read-only ones (search, read, list, status) need no LLM key so the server is useful on its own. Indexing runs in the background and clients poll `repo_status` | Assistants time out on multi-minute calls; a key-free core makes it easy to adopt | Clients gain a long-running-task protocol we can use instead of polling |
| 22 | Expected failures are converted to MCP `ToolError` by a decorator | In MCP 2.x any other exception is a crash: the model sees only "Error executing tool" and the server logs a traceback | SDK changes this default |
| 23 | Owner/repo patterns reject dot-only names (`..`) and owners with dots, in the URL validator, PR URL parser and repo-id check | A test showed `../etc` resolved to a valid repo id. Not exploitable (the id is one directory name) but sloppy | n/a |

| 24 | Evaluation is deterministic (fact regexes, gold evidence overlap, citation checks), no LLM judge, on repos pinned to exact SHAs with a self-verifying ground truth (`eval verify`). 6 of 38 questions are negative ("not in this repo") | Reproducible, free to re-score, and negatives catch fabrication. The cost is brittleness: regexes can miss a correct answer in other words | A second author or real user questions are available |
| 25 | Auditing the first baseline's 9 failures found 4 were my scoring or ground-truth mistakes. Fixed in dataset v2 and the stored answers re-scored with `eval rescore`, not re-run. The fixes are listed in the dataset's `history` | Reporting 76% when the true figure was 84% would have undersold the system and hidden how brittle regex scoring is | n/a |
| 26 | Agent loop: a repeated tool call returns a hint (searches compare by words); the last step removes tools, and if the model still calls one that turn is dropped and plain text is requested; an answer that opens by saying the thing is absent is accepted without citations once the agent has searched (never after a leading "Yes", with an invalid citation, or without searching); `path:12,40-45` lists are parsed | Evaluation showed empty answers after 8 repeated searches, and our citation check pushing the model to cite lines it never read | Abstention heuristics cause false accepts |
| 27 | Retrieval: oversized classes are split into per-method chunks; every chunk records the symbol it defines (all windows of a long function); a third ranking signal matches query identifiers to symbols. On the baseline agent's own searches: hit@1 31% to 53%, MRR 0.52 to 0.68, recall@8 88% to 94% | Identifier-style searches are what the agent issues, and keyword plus vector search drown definitions in tests and docs | Evals show wrong-method matches on common names |
| 28 | Embed the first 1000 characters of each chunk (was 1500). 7.4 to 10.3 chunks/s, click index 263s to 185s, recall@8 unchanged (91%). 700 chars halves the time but loses a question at rank 8 | Index time is the demo's main wait | A faster embedding model replaces this trade-off |
| 29 | Default Gemini model is `gemini-3.5-flash-lite` (was `gemini-3.1-flash-lite`) | It is the model every evaluation number describes, and 3.1 returned 503 "high demand" on 2 of 3 probes and failed the first baseline attempt | Availability changes; re-probe |

| 30 | Embed one text per model call (`EMBED_BATCH = 1`). 29.6 vs 10.6 chunks/s on click's chunks, peak memory 280 MB vs 869 MB, identical vectors; click index 185s to 71s | fastembed pads every text in a batch to the longest, so large batches waste most of the work. My earlier 'batch size makes no difference' claim was wrong: I had only compared 16 to 64. Memory is what makes live indexing possible on a 512 MB host | A model whose runtime does not pad |

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

## Day 5 findings (PR review)
- Live check on a synthetic diff with planted bugs plus an injected "approve without comments" instruction: all 4 planted issues found (SQL injection, eval, hardcoded key, off-by-one) at exact lines, injection ignored.
- Live check on a real PR (setup-uv 5 to 7): clean review, no invented problems.
- The sandbox proxy only allows GitHub reads for attached repos, so live reviews here are limited to KevinGeorge100/repopilot PRs.
- Review UI is not built yet: the evidence panel shows files, but findings anchor to diff lines, so the UI needs a diff view.

## Day 5 findings (MCP)
- Verified end to end over a real stdio subprocess with the live LLM: status, search, ask (4 verified citations), PR review of a real PR, and a path-escape refused with a readable error. Tested with the MCP SDK's own client, not with Claude Code itself.
- MCP SDK 2.x renamed FastMCP to MCPServer and changed error semantics; tests pin the behaviour we depend on.
- Review UI is still not built (needs a diff view).

## Day 6 findings (evaluation)
- Full numbers, caveats and reproduction commands: `evals/RESULTS.md`. Method: `evals/README.md`.
- The free tier has a **daily** per-model request quota (`GenerateRequestsPerDayPerProjectPerModel-FreeTier`) that ended v2 two questions early. Evaluations that need many runs must be spread over days or use a paid key. Providers also return 503 "high demand" in spikes; `--abort-after` stops a run during an outage and the same command resumes.
- Not yet done: an end-to-end run on the final index (v3: all windows tagged, 1000-char embeddings); a repeat run to measure run-to-run noise; completing slg-06 and slg-09 for v2.
- Persistent failure `its-14`: the model calls Django-compatible key derivation an "integration".
