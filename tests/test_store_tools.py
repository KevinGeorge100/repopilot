from pathlib import Path

import pytest

from repopilot.chunker import chunk_file
from repopilot.embed import HashEmbedder
from repopilot.store import Store
from repopilot.tools import ToolError, list_tree, read_file, search_code

FILES = {
    "cli/args.py": "def parse_args(argv):\n    '''Parse command line arguments.'''\n    return argv[1:]\n",
    "db/conn.py": "def connect_database(url):\n    '''Open a database connection pool.'''\n    return url\n",
    "web/render.py": "def render_template(name):\n    '''Render an HTML template.'''\n    return name\n",
}


@pytest.fixture
def repo(tmp_path: Path):
    for rel, src in FILES.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(src)
    emb = HashEmbedder()
    store = Store()
    for rel, src in FILES.items():
        store.add(chunk_file(rel, src), emb)
    return tmp_path, store, emb


def test_search_finds_relevant_chunk_first(repo):
    _, store, emb = repo
    hits = search_code(store, emb, "how are command line arguments parsed", k=3)
    assert hits[0]["citation"].startswith("cli/args.py:")
    hits = search_code(store, emb, "connect_database")
    assert hits[0]["citation"].startswith("db/conn.py:")


def test_search_empty_and_punctuation_safe(repo):
    _, store, emb = repo
    with pytest.raises(ToolError):
        search_code(store, emb, "   ")
    assert search_code(store, emb, 'foo" OR ) NEAR(')  # must not raise FTS syntax errors


def test_read_file_numbers_lines_and_clamps(repo):
    root, *_ = repo
    r = read_file(root, "cli/args.py", 1, 2)
    assert r["citation"] == "cli/args.py:1-2" and r["text"].startswith("1: def parse_args")
    assert read_file(root, "cli/args.py", 1, 999)["citation"] == "cli/args.py:1-3"


@pytest.mark.parametrize("bad", ["../etc/passwd", "/etc/passwd", "cli/../../x", ".git/config"])
def test_read_file_blocks_escape_and_excluded(repo, bad):
    root, *_ = repo
    with pytest.raises(ToolError):
        read_file(root, bad)


def test_list_tree(repo):
    root, *_ = repo
    t = list_tree(root, ".", 2)
    assert "cli/" in t["entries"] and "  args.py" in t["entries"]
    with pytest.raises(ToolError):
        list_tree(root, "cli/args.py")


def test_path_prior_prefers_code_over_docs_and_changelogs():
    from repopilot.store import path_prior

    assert path_prior("src/a.py") > path_prior("docs/a.md") > path_prior("CHANGES.md")


def test_search_results_are_line_numbered(repo):
    _, store, emb = repo
    text = search_code(store, emb, "parse_args")[0]["text"]
    assert text.splitlines()[0].startswith("1: def parse_args")
