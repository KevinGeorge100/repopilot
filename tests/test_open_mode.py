import os
import time
from pathlib import Path

import pytest
from test_server import URL, fixture_repo, make_client, wait_ready  # noqa: F401  (fixture_repo is a fixture)

from repopilot.embed import HashEmbedder
from repopilot.indexing import IndexManager
from repopilot.ingest import (
    MAX_REPO_BYTES,
    _tree_bytes,
    chunk_repo,
    clone,
    iter_source_files,
)


def test_indexer_skips_symlinks_so_a_hostile_repo_cannot_read_host_files(tmp_path: Path):
    secret = tmp_path / "secret.py"
    secret.write_text("def leaked():\n    return 'TOP-SECRET'\n")
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "ok.py").write_text("def fine():\n    return 1\n")
    os.symlink(secret, repo / "link.py")
    os.symlink(tmp_path, repo / "dirlink")
    assert [p.name for p in iter_source_files(repo)] == ["ok.py"]
    assert all("TOP-SECRET" not in c.text for c in chunk_repo(repo))


def test_tree_size_ignores_git_and_symlinks(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "pack").write_bytes(b"x" * 5000)
    (tmp_path / "a.py").write_bytes(b"x" * 100)
    os.symlink(tmp_path / "a.py", tmp_path / "b.py")
    assert _tree_bytes(tmp_path) == 100
    assert MAX_REPO_BYTES >= 100 * 1024 * 1024


def test_clone_rejects_non_github_urls(tmp_path: Path):
    with pytest.raises(ValueError):
        clone("https://evil.example/a/b", tmp_path / "x")


def test_prune_keeps_newest_user_repos_and_never_evicts_protected(tmp_path: Path):
    m = IndexManager(tmp_path, HashEmbedder(), protected=frozenset({"keep--me"}), max_user_repos=2)
    idx = tmp_path / "index"
    idx.mkdir()
    for i, rid in enumerate(["keep--me", "a--one", "b--two", "c--three"]):
        db = idx / f"{rid}.db"
        db.write_text("x")
        (tmp_path / "repos" / rid).mkdir(parents=True)
        os.utime(db, (time.time() - 100 + i, time.time() - 100 + i))
    gone = m.prune()
    assert gone == ["a--one"]
    assert not (tmp_path / "repos" / "a--one").exists()
    assert (idx / "keep--me.db").exists() and (idx / "c--three.db").exists() and (idx / "b--two.db").exists()


def test_touch_makes_a_repo_the_most_recently_used(tmp_path: Path):
    m = IndexManager(tmp_path, HashEmbedder(), max_user_repos=1)
    idx = tmp_path / "index"
    idx.mkdir()
    for rid, age in [("old--one", 50), ("new--two", 10)]:
        (idx / f"{rid}.db").write_text("x")
        os.utime(idx / f"{rid}.db", (time.time() - age, time.time() - age))
    m.touch("old--one")
    assert m.prune() == ["new--two"]


def test_open_mode_indexes_new_repos_and_reports_limits(tmp_path: Path, fixture_repo: Path):  # noqa: F811
    c = make_client(tmp_path, fixture_repo, demo_mode=False, daily_index_cap=1, max_chunks=500)
    cfg = c.get("/api/config").json()
    assert cfg["indexing"] is True and cfg["indexing_remaining"] == 1 and cfg["max_chunks"] == 500
    r = c.post("/api/repos", json={"url": URL})
    assert r.status_code == 202
    assert wait_ready(c, r.json()["id"])["status"] == "ready"
    # the same repo again is free; a different one is refused once today's cap is spent
    assert c.post("/api/repos", json={"url": URL}).status_code == 202
    other = c.post("/api/repos", json={"url": "https://github.com/acme/other"})
    assert other.status_code == 429 and "Today" in other.json()["detail"]
    assert c.get("/api/config").json()["indexing_remaining"] == 0


def test_failed_clone_shows_a_plain_message(tmp_path: Path):
    from fastapi.testclient import TestClient

    from repopilot.server import create_app

    def boom(url, dest):
        raise ValueError("Could not download this repository. Check that it exists and is public.")

    c = TestClient(create_app(tmp_path / "w", embedder=HashEmbedder(), clone_fn=boom, demo_mode=False))
    rid = c.post("/api/repos", json={"url": URL}).json()["id"]
    st = wait_ready(c, rid)
    assert st["status"] == "error" and st["error"].startswith("Could not download")


# ---- instant-ready indexing: ask first, vectors follow ----------------------------------------------------
def test_text_only_index_is_searchable_then_vectors_are_added(tmp_path: Path):
    from repopilot.chunker import chunk_file
    from repopilot.store import Store

    emb = HashEmbedder()
    store = Store(tmp_path / "t.db")
    store.add_text(chunk_file("cli.py", "def parse_args(argv):\n    return argv[1:]\n\n\ndef main():\n    return 0\n"))
    assert store.pending() == 2
    assert store.search("parse_args", emb)[0].chunk.symbol == "parse_args"  # keyword + name search, no vectors
    store.embed_pending(emb, batch=1)
    assert store.pending() == 0
    assert store.search("parse arguments", emb)  # vector signal now contributes
    store.embed_pending(emb)  # nothing left: a no-op


class SlowEmbedder(HashEmbedder):
    """Blocks embedding until released, so a test can look at the repo while vectors are still pending."""

    def __init__(self) -> None:
        super().__init__()
        import threading

        self.gate = threading.Event()

    def embed(self, texts):
        self.gate.wait(10)
        return super().embed(texts)


def test_repo_is_ready_before_embedding_finishes(tmp_path: Path, fixture_repo: Path):  # noqa: F811
    import shutil

    emb = SlowEmbedder()

    def fake_clone(url, dest):
        shutil.copytree(fixture_repo, dest, dirs_exist_ok=True)
        return dest

    m = IndexManager(tmp_path, emb, fake_clone)
    job = m.start(URL)
    end = time.time() + 10
    while job.status != "ready" and time.time() < end:
        time.sleep(0.02)
    assert job.status == "ready" and job.chunks > 0
    assert job.embedded < job.embed_total  # vectors are still being computed in the background
    emb.gate.set()
    end = time.time() + 10
    while job.embedded < job.embed_total and time.time() < end:
        time.sleep(0.02)
    assert job.embedded == job.embed_total > 0
