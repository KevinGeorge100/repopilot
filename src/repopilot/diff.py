"""Parse unified diffs (GitHub .diff output) into new-side line numbers, and fetch a PR's diff."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

import httpx

PR_URL = re.compile(r"^https://github\.com/([\w.-]+)/([\w.-]+)/pull/(\d{1,7})/?$")
HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
MAX_DIFF_BYTES = 1_500_000
MAX_FILES = 60
MAX_LINES_PER_FILE = 800


@dataclass(frozen=True)
class DiffLine:
    kind: str  # "+" added, "-" removed, " " context
    new_no: int | None
    old_no: int | None
    text: str


@dataclass
class Hunk:
    header: str
    lines: list[DiffLine] = field(default_factory=list)


@dataclass
class FileDiff:
    path: str  # new path (old path for deleted files)
    status: str = "modified"  # added | deleted | modified | renamed
    old_path: str | None = None
    binary: bool = False
    hunks: list[Hunk] = field(default_factory=list)
    truncated: bool = False

    @property
    def added_lines(self) -> set[int]:
        return {ln.new_no for h in self.hunks for ln in h.lines if ln.kind == "+" and ln.new_no is not None}

    @property
    def visible_lines(self) -> set[int]:
        return {ln.new_no for h in self.hunks for ln in h.lines if ln.new_no is not None}


@dataclass
class ParsedDiff:
    files: list[FileDiff]
    omitted_files: int = 0

    def get(self, path: str) -> FileDiff | None:
        return next((f for f in self.files if f.path == path), None)


def parse_pr_url(url: str) -> tuple[str, str, int]:
    m = PR_URL.match(url.strip())
    if not m:
        raise ValueError("Use a pull request URL like https://github.com/owner/repo/pull/123")
    return m.group(1), m.group(2), int(m.group(3))


def _strip_prefix(p: str) -> str | None:
    p = p.split("\t")[0].strip().strip('"')
    if p == "/dev/null":
        return None
    return p[2:] if p[:2] in ("a/", "b/") else p


def parse_diff(text: str, max_files: int = MAX_FILES, max_lines_per_file: int = MAX_LINES_PER_FILE) -> ParsedDiff:
    lines = text.splitlines()
    files: list[FileDiff] = []
    omitted = 0
    cur: FileDiff | None = None
    skipping = False
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("diff --git "):
            m = re.match(r"^diff --git a/(.+) b/(.+)$", line)
            skipping = len(files) >= max_files
            if skipping:
                omitted += 1
                cur = None
            else:
                cur = FileDiff(path=m.group(2) if m else line[11:].strip(), old_path=m.group(1) if m else None)
                files.append(cur)
            i += 1
            continue
        if cur is None:
            i += 1
            continue
        if line.startswith("new file mode"):
            cur.status = "added"
        elif line.startswith("deleted file mode"):
            cur.status = "deleted"
        elif line.startswith("rename from "):
            cur.status, cur.old_path = "renamed", line[12:].strip()
        elif line.startswith("rename to "):
            cur.path = line[10:].strip()
        elif line.startswith(("Binary files", "GIT binary patch")):
            cur.binary = True
        elif line.startswith("--- ") and not cur.hunks:
            old = _strip_prefix(line[4:])
            if old is None:
                cur.status = "added"
            else:
                cur.old_path = old
        elif line.startswith("+++ ") and not cur.hunks:
            new = _strip_prefix(line[4:])
            if new is None:
                cur.status = "deleted"
                cur.path = cur.old_path or cur.path
            else:
                cur.path = new
        elif (hm := HUNK.match(line)):
            old_no, old_len = int(hm.group(1)), int(hm.group(2) or 1)
            new_no, new_len = int(hm.group(3)), int(hm.group(4) or 1)
            hunk = Hunk(header=line)
            i += 1
            # Header counts tell us exactly where the hunk ends, so a removed line like "-- x"
            # (rendered "--- x") is never mistaken for a file header.
            while i < len(lines) and (old_len > 0 or new_len > 0):
                body = lines[i]
                tag = body[:1]
                if tag == "\\":  # "\ No newline at end of file"
                    i += 1
                    continue
                text_ = body[1:]
                total = sum(len(h.lines) for h in cur.hunks) + len(hunk.lines)
                keep = total < max_lines_per_file
                if tag == "+":
                    if keep:
                        hunk.lines.append(DiffLine("+", new_no, None, text_))
                    new_no, new_len = new_no + 1, new_len - 1
                elif tag == "-":
                    if keep:
                        hunk.lines.append(DiffLine("-", None, old_no, text_))
                    old_no, old_len = old_no + 1, old_len - 1
                else:
                    if keep:
                        hunk.lines.append(DiffLine(" ", new_no, old_no, text_))
                    old_no, new_no, old_len, new_len = old_no + 1, new_no + 1, old_len - 1, new_len - 1
                if not keep:
                    cur.truncated = True
                i += 1
            cur.hunks.append(hunk)
            continue
        i += 1
    return ParsedDiff(files, omitted)


def render_for_model(pd: ParsedDiff, max_chars: int = 60_000) -> tuple[str, bool]:
    """Render with NEW-side line numbers so findings can cite exact lines. Returns (text, truncated)."""
    out: list[str] = []
    used = 0
    truncated = pd.omitted_files > 0
    for f in pd.files:
        head = f"### {f.path} ({f.status}{', binary' if f.binary else ''})"
        if f.old_path and f.old_path != f.path and f.status == "renamed":
            head += f" renamed from {f.old_path}"
        block = [head]
        for h in f.hunks:
            block.append(h.header)
            for ln in h.lines:
                if ln.kind == "-":
                    block.append(f"-      | {ln.text}")
                else:
                    block.append(f"{ln.kind}{ln.new_no:>5} | {ln.text}")
        if f.truncated:
            block.append("[file truncated]")
        text = "\n".join(block)
        if used + len(text) > max_chars:
            truncated = True
            out.append(f"### {f.path} ({f.status}): omitted, diff too large")
            continue
        used += len(text)
        out.append(text)
    if pd.omitted_files:
        out.append(f"[{pd.omitted_files} more files omitted]")
    return "\n\n".join(out), truncated


def fetch_pr_diff(owner: str, repo: str, number: int, client: httpx.Client | None = None) -> str:
    """Download a public PR's unified diff from the GitHub REST API (size-capped).

    Uses the API rather than github.com/<pr>.diff because that URL redirects to a second host.
    Set GITHUB_TOKEN to raise the unauthenticated limit (60 requests/hour per IP).
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{number}"
    headers = {"Accept": "application/vnd.github.diff", "X-GitHub-Api-Version": "2022-11-28"}
    if token := os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    own = client is None
    client = client or httpx.Client(timeout=30, follow_redirects=True)
    try:
        with client.stream("GET", url, headers=headers) as r:
            if r.status_code == 404:
                raise ValueError("Pull request not found. It must be public.")
            if r.status_code in (406, 422):
                raise ValueError("This pull request's diff is too large for GitHub to generate.")
            if r.status_code in (403, 429):
                hint = "" if token else " Set GITHUB_TOKEN to raise the limit."
                raise RuntimeError(f"GitHub refused the request (rate limit or access).{hint}")
            if r.status_code >= 400:
                raise RuntimeError(f"GitHub returned {r.status_code} for the diff")
            buf = bytearray()
            for chunk in r.iter_bytes():
                buf.extend(chunk)
                if len(buf) > MAX_DIFF_BYTES:
                    raise ValueError("This pull request's diff is too large to review (over 1.5 MB).")
            return buf.decode("utf-8", errors="replace")
    except httpx.HTTPError as e:
        raise RuntimeError(f"Could not download the diff: {type(e).__name__}") from e
    finally:
        if own:
            client.close()
