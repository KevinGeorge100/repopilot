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


@pytest.mark.parametrize("url", ["--upload-pack=evil", "file:///etc/passwd", "https://evil.com/a/b", "git@github.com:a/b", "https://github.com/../x", "https://github.com/a/..", "https://github.com/.x/y", "https://github.com/a/."])
def test_invalid_urls_rejected(url):
    with pytest.raises(ValueError):
        validate_url(url)


# ---- symbols and class splitting (added with name-based retrieval) -------------
def _method(name: str, body_lines: int = 30) -> str:
    return f"    def {name}(self):\n" + "".join(f"        x{i} = {i}\n" for i in range(body_lines)) + "        return 0\n\n"


BIG_CLASS = "import os\n\n\nclass Big:\n    '''Docstring.'''\n    attr = 1\n\n" + _method("alpha") + _method("beta") + _method("gamma")


def test_chunks_record_the_symbol_they_define():
    chunks = chunk_file("a.py", PY)
    assert {c.symbol for c in chunks if c.kind == "definition"} == {"foo", "Bar"}
    assert all(c.symbol is None for c in chunks if c.kind == "window")  # the import/constant gap defines nothing


def test_an_oversized_class_is_split_into_methods_with_their_own_symbols():
    chunks = chunk_file("big.py", BIG_CLASS)
    methods = {c.symbol: c for c in chunks if c.kind == "definition"}
    assert set(methods) == {"alpha", "beta", "gamma"}
    header = [c for c in chunks if c.symbol == "Big"]
    assert len(header) == 1 and header[0].kind == "window" and "Docstring" in header[0].text
    for name, c in methods.items():  # exact ranges: the chunk starts at its def line
        assert c.text.splitlines()[0].strip() == f"def {name}(self):"
    lines = BIG_CLASS.splitlines()
    covered = {n for c in chunks for n in range(c.start_line, c.end_line + 1)}
    assert [n for n, ln in enumerate(lines, 1) if ln.strip() and n not in covered] == []  # nothing lost


def test_an_oversized_function_becomes_windows_that_all_carry_its_name():
    src = "def huge():\n" + "".join(f"    y{i} = {i}\n" for i in range(150)) + "    return 1\n"
    chunks = chunk_file("h.py", src)
    assert len(chunks) > 2 and all(c.kind == "window" for c in chunks)
    assert all(c.symbol == "huge" for c in chunks)  # a question about code deep inside still matches the name


def test_keyword_tokens_never_become_one_line_definitions():
    """Regression: the `class` keyword inside a class node once matched as a definition of its own."""
    chunks = chunk_file("big.py", BIG_CLASS)
    assert all(c.end_line > c.start_line for c in chunks if c.kind == "definition")
    assert not any(c.text.strip() == "class Big:" and c.kind == "definition" for c in chunks)


def test_javascript_functions_get_symbols_too():
    src = "export default function slugify(input) {\n  return input.trim();\n}\n\nfunction other() {\n  return 1;\n}\n"
    names = {c.symbol for c in chunk_file("index.js", src) if c.kind == "definition"}
    assert names == {"slugify", "other"}
