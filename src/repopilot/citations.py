"""Citation extraction + verification (decision #6: the headline quality metric)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# `path:12`, `path:12-20`, and lists such as `path:12,40-45` (models write them; each range is verified separately)
CITE_RE = re.compile(r"(?<![\w/:.])([\w][\w./\-]*\.[A-Za-z]\w*):(\d+(?:-\d+)?(?:\s*,\s*\d+(?:-\d+)?)*)(?!\d)")


@dataclass(frozen=True)
class Citation:
    path: str
    start: int
    end: int

    def __str__(self) -> str:
        return f"{self.path}:{self.start}-{self.end}"


@dataclass
class CitationReport:
    cited: list[Citation] = field(default_factory=list)
    invalid: list[tuple[str, str]] = field(default_factory=list)  # (citation, reason)
    ungrounded: list[str] = field(default_factory=list)  # real lines the agent never retrieved
    abstained: bool = False  # an honest "not in this repo" answer: nothing to cite, and that is fine

    @property
    def ok(self) -> bool:
        return (bool(self.cited) or self.abstained) and not self.invalid and not self.ungrounded

    @property
    def validity(self) -> float:
        total = len(self.cited) + len(self.invalid)
        return 1.0 if total == 0 else len(self.cited) / total


# An answer that opens by saying the thing is absent. A leading "Yes" never counts: "Yes, via a custom class"
# is a claim about the code and needs evidence like any other.
ABSENCE_RE = re.compile(
    r"^(?!\s*yes\b)[\s\S]{0,300}?\b(does not|doesn'?t|do not|don'?t|is not|isn'?t|are not|aren'?t|cannot|can'?t|"
    r"no (built-in|support|mention|evidence|such|integration)|"
    r"not (found|mentioned|provide|support|supported|include|contain|part|implemented|present|available))\b",
    re.IGNORECASE,
)


def looks_like_absence(answer: str) -> bool:
    return bool(ABSENCE_RE.search(answer))


def extract(text: str) -> list[Citation]:
    out: list[Citation] = []
    for m in CITE_RE.finditer(text):
        for part in m.group(2).split(","):
            lo, _, hi = part.strip().partition("-")
            out.append(Citation(m.group(1), int(lo), int(hi or lo)))
    return list(dict.fromkeys(out))


def _count_lines(p: Path) -> int | None:
    try:
        return len(p.read_text(encoding="utf-8").splitlines())
    except (UnicodeDecodeError, OSError):
        return None


def verify(answer: str, root: Path, seen: list[Citation]) -> CitationReport:
    """Check that each citation exists in the repo and was actually retrieved by the agent."""
    rep = CitationReport()
    root = root.resolve()
    for c in extract(answer):
        p = (root / c.path).resolve()
        if root not in p.parents or not p.is_file():
            rep.invalid.append((str(c), "file does not exist"))
            continue
        n = _count_lines(p)
        if n is None or c.start < 1 or c.end < c.start or c.end > n:
            rep.invalid.append((str(c), f"line range outside file (1-{n})"))
            continue
        rep.cited.append(c)
        if not any(s.path == c.path and s.start <= c.end and c.start <= s.end for s in seen):
            rep.ungrounded.append(str(c))
    return rep
