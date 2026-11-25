import httpx
import pytest
from diffs import SAMPLE_DIFF

from repopilot.diff import fetch_pr_diff, parse_diff, parse_pr_url, render_for_model


def test_parses_files_status_and_new_side_line_numbers():
    pd = parse_diff(SAMPLE_DIFF)
    by = {f.path: f for f in pd.files}
    assert set(by) == {"app.py", "new.txt", "old.txt", "b.py", "img.png", "q.sql"}
    assert by["new.txt"].status == "added" and by["old.txt"].status == "deleted"
    assert by["b.py"].status == "renamed" and by["b.py"].old_path == "a.py"
    assert by["img.png"].binary
    app = by["app.py"]
    assert app.added_lines == {3, 4, 5, 23}  # def load (3), data (4), eval (5), trailing (23)
    assert {1, 2, 6, 7} <= app.visible_lines  # context lines are visible but not added
    assert 1 not in app.added_lines


def test_removed_line_that_looks_like_a_file_header_is_not_misparsed():
    f = {x.path: x for x in parse_diff(SAMPLE_DIFF).files}["q.sql"]
    assert [(ln.kind, ln.text) for ln in f.hunks[0].lines] == [("-", "-- sql comment"), ("+", "++ sql comment2")]
    assert f.added_lines == {1}


def test_file_and_line_caps_are_reported_not_silent():
    big = "\n".join(
        ["diff --git a/x.py b/x.py", "--- a/x.py", "+++ b/x.py", "@@ -0,0 +1,50 @@"] + [f"+l{i}" for i in range(50)]
    )
    pd = parse_diff(big, max_lines_per_file=10)
    assert pd.files[0].truncated and len(pd.files[0].hunks[0].lines) == 10
    many = "\n".join(f"diff --git a/f{i} b/f{i}\n--- a/f{i}\n+++ b/f{i}\n@@ -0,0 +1 @@\n+x" for i in range(5))
    pd = parse_diff(many, max_files=2)
    assert len(pd.files) == 2 and pd.omitted_files == 3
    _, truncated = render_for_model(pd)
    assert truncated


def test_render_uses_new_side_numbers():
    text, truncated = render_for_model(parse_diff(SAMPLE_DIFF))
    assert "+    4 |     data = open(path).read()" in text and not truncated
    assert "-      | def load(path):" in text
    assert "renamed from a.py" in text


def test_garbage_input_yields_empty_diff():
    assert parse_diff("not a diff at all").files == []


@pytest.mark.parametrize("url", ["https://github.com/a/b/pull/12", "https://github.com/a-b/c.d/pull/7/"])
def test_valid_pr_urls(url):
    assert parse_pr_url(url)[2] in (12, 7)


@pytest.mark.parametrize(
    "url", ["https://evil.com/a/b/pull/1", "https://github.com/a/b/issues/1", "https://github.com/a/b/pull/x", "file:///etc/passwd", "https://github.com/../b/pull/1", "https://github.com/a/../pull/1"]
)
def test_invalid_pr_urls(url):
    with pytest.raises(ValueError):
        parse_pr_url(url)


def client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)


def test_fetch_uses_the_api_with_diff_accept_header_and_optional_token(monkeypatch):
    seen = {}

    def handler(req):
        seen.update(url=str(req.url), accept=req.headers["accept"], auth=req.headers.get("authorization"))
        return httpx.Response(200, text="diff")

    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    assert fetch_pr_diff("a", "b", 7, client(handler)) == "diff"
    assert seen == {"url": "https://api.github.com/repos/a/b/pulls/7", "accept": "application/vnd.github.diff", "auth": None}
    monkeypatch.setenv("GITHUB_TOKEN", "t0k")
    fetch_pr_diff("a", "b", 7, client(handler))
    assert seen["auth"] == "Bearer t0k"


def test_fetch_error_mapping(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    with pytest.raises(ValueError, match="not found"):
        fetch_pr_diff("a", "b", 1, client(lambda r: httpx.Response(404)))
    with pytest.raises(ValueError, match="too large for GitHub"):
        fetch_pr_diff("a", "b", 1, client(lambda r: httpx.Response(406)))
    with pytest.raises(ValueError, match="too large to review"):
        fetch_pr_diff("a", "b", 1, client(lambda r: httpx.Response(200, content=b"x" * 1_600_000)))
    with pytest.raises(RuntimeError, match="GITHUB_TOKEN"):
        fetch_pr_diff("a", "b", 1, client(lambda r: httpx.Response(403)))
    with pytest.raises(RuntimeError, match="returned 500"):
        fetch_pr_diff("a", "b", 1, client(lambda r: httpx.Response(500)))

    def boom(req):
        raise httpx.ConnectError("down")

    with pytest.raises(RuntimeError, match="Could not download"):
        fetch_pr_diff("a", "b", 1, client(boom))
