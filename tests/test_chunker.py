import pytest

from repopilot.chunker import chunk_file
from repopilot.ingest import validate_url

PY = '''import os

X = 1

def foo():
    return 1


class Bar:
    def baz(self):
        return 2
'''


def test_definitions_have_exact_line_ranges():
    chunks = chunk_file("a.py", PY)
    by_text = {c.text.splitlines()[0]: c for c in chunks}
    foo = by_text["def foo():"]
    assert (foo.start_line, foo.end_line, foo.kind) == (5, 6, "definition")
    bar = by_text["class Bar:"]
    assert bar.start_line == 9 and bar.end_line == 11


def test_chunks_cover_source_lines_and_citations_resolve():
    lines = PY.splitlines()
    for c in chunk_file("a.py", PY):
        assert "\n".join(lines[c.start_line - 1 : c.end_line]) == c.text
        assert c.citation == f"a.py:{c.start_line}-{c.end_line}"


def test_unknown_extension_falls_back_to_windows():
    text = "\n".join(f"line {i}" for i in range(150))
    chunks = chunk_file("notes.unknownext", text)
    assert len(chunks) >= 3 and all(c.kind == "window" for c in chunks)


def test_empty_file_yields_no_chunks():
    assert chunk_file("a.py", "  \n") == []


@pytest.mark.parametrize("url", ["https://github.com/pallets/flask", "https://github.com/a/b.git"])
def test_valid_urls(url):
    assert validate_url(url) == url


@pytest.mark.parametrize("url", ["--upload-pack=evil", "file:///etc/passwd", "https://evil.com/a/b", "git@github.com:a/b"])
def test_invalid_urls_rejected(url):
    with pytest.raises(ValueError):
        validate_url(url)
