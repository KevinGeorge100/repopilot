# Security

RepoPilot clones public repositories and sends code snippets to a third-party LLM provider.

- Report vulnerabilities privately through GitHub's "Report a vulnerability" (Security tab), not public issues.
- Repository content is treated as untrusted input (prompt injection). Tools are read-only and never execute repo code.
- Only `https://github.com/<owner>/<repo>` URLs are accepted; git is invoked with `--` to prevent option injection.
- Never commit API keys. Keys come from environment variables or the host's secret store.
