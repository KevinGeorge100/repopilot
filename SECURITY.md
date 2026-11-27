# Security

RepoPilot clones public repositories and sends code snippets to a third-party LLM provider.

- Report vulnerabilities privately through GitHub's "Report a vulnerability" (Security tab), not public issues.
- Repository content is treated as untrusted input (prompt injection). Tools are read-only and never execute repo code.
- Only `https://github.com/<owner>/<repo>` URLs are accepted; git is invoked with `--` to prevent option injection.
- Never commit API keys. Keys come from environment variables or the host's secret store.

## Hosted app: visitors can add public repositories
Open mode lets anyone make the server download and index a public GitHub repo, so the code that reads it is
defensive: symlinks are written as plain text by git and skipped by the indexer (a hostile repo cannot expose server
files such as the environment), nothing from a repo is ever executed, downloads time out and are size-limited, private
repos fail without a password prompt, and per-visitor, per-day and on-disk limits bound the cost. Set
`REPOPILOT_DEMO_MODE=1` to turn visitor indexing off.
