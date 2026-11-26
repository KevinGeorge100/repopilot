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


# ---- name-based retrieval ------------------------------------------------------
def _store_with(chunks):
    emb, store = HashEmbedder(), Store()
    store.add(chunks, emb)
    return store, emb


def test_a_definition_outranks_docs_and_tests_that_merely_mention_the_name():
    from repopilot.chunker import Chunk

    chunks = [
        Chunk("docs/prompts.md", 1, 5, "prompt prompt prompt: how to prompt the user, prompt text, prompt options", "window"),
        Chunk("tests/test_termui.py", 1, 9, "def test_prompt():\n    prompt('x')\n    prompt('y')\n    prompt('z')", "definition", "test_prompt"),
        Chunk("src/termui.py", 100, 140, "def prompt(text, default=None):\n    '''Ask for input.'''\n    return input(text)", "definition", "prompt"),
        Chunk("src/other.py", 1, 5, "def unrelated():\n    return 1", "definition", "unrelated"),
    ]
    store, emb = _store_with(chunks)
    hits = store.search("def prompt(", emb, k=3)
    assert hits[0].chunk.path == "src/termui.py" and hits[0].chunk.symbol == "prompt"


def test_symbol_survives_a_round_trip_and_unrelated_names_add_nothing():
    from repopilot.chunker import Chunk

    store, emb = _store_with([Chunk("a.py", 1, 3, "def foo():\n    return 1", "definition", "foo")])
    assert store.has_symbols and store.search("foo", emb)[0].chunk.symbol == "foo"
    assert store.search("something else entirely", emb)[0].chunk.symbol == "foo"  # still found by the other signals


def test_an_index_built_before_symbols_existed_still_searches(tmp_path):
    import sqlite3

    db = tmp_path / "old.db"
    con = sqlite3.connect(db)
    con.executescript(
        """CREATE TABLE chunks(id INTEGER PRIMARY KEY, path TEXT, start_line INT, end_line INT, kind TEXT, text TEXT, vec BLOB);
           CREATE VIRTUAL TABLE chunks_fts USING fts5(text, path, content='chunks', content_rowid='id', tokenize="unicode61 tokenchars '_'");"""
    )
    emb = HashEmbedder()
    vec = emb.embed(["def foo(): return 1"])[0].tobytes()
    con.execute("INSERT INTO chunks VALUES(1,'a.py',1,2,'definition','def foo(): return 1',?)", (vec,))
    con.execute("INSERT INTO chunks_fts(rowid,text,path) VALUES(1,'def foo(): return 1','a.py')")
    con.commit()
    con.close()
    store = Store(db)
    assert not store.has_symbols
    hit = store.search("foo", emb)[0]
    assert hit.chunk.citation == "a.py:1-2" and hit.chunk.symbol is None


def test_fast_embedder_embeds_one_sequence_at_a_time_and_normalises():
    """Batching pads every text to the longest in the batch: 3x slower and 3x the memory for identical vectors."""
    import numpy as np

    from repopilot.embed import EMBED_BATCH, FastEmbedder

    seen = {}

    class FakeModel:
        def embed(self, texts, batch_size=256):
            seen["batch_size"] = batch_size
            return [np.array([3.0, 4.0] + [0.0] * 382, dtype=np.float32) for _ in texts]

    emb = FastEmbedder()
    emb._model = FakeModel()
    vecs = emb.embed(["a", "b"])
    assert EMBED_BATCH == 1 and seen["batch_size"] == 1
    assert vecs.shape == (2, 384) and abs(float(np.linalg.norm(vecs[0])) - 1.0) < 1e-6
