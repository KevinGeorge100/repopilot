"""Deterministic scoring and aggregation. No LLM judge: every number is reproducible from a trace."""
from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass, field
from statistics import mean
from typing import Any

from .dataset import Question


@dataclass
class Score:
    passed: bool
    fact_pass: bool
    evidence_hit: bool | None  # None for negative questions
    citations_ok: bool
    n_valid: int = 0
    n_invalid: int = 0
    n_ungrounded: int = 0
    avg_span: float | None = None
    missing_facts: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _overlaps(c: dict, g) -> bool:
    return c["path"].lstrip("./") == g.path and c["start"] <= g.end and g.start <= c["end"]


def score_answer(q: Question, payload: dict[str, Any]) -> Score:
    """Score one agent result (the dict from AgentResult.to_dict) against a question."""
    answer = payload.get("answer", "")
    cites = payload.get("citations", {})
    valid = cites.get("valid", [])
    n_invalid, n_ungrounded = len(cites.get("invalid", [])), len(cites.get("ungrounded", []))

    missing = [p for p in q.facts if not re.search(p, answer, re.IGNORECASE | re.DOTALL)]
    fact_pass = not missing
    # Positive questions must cite something. Negative ones may cite related code or nothing.
    citations_ok = n_invalid == 0 and n_ungrounded == 0 and (q.negative or len(valid) > 0)
    hit = None if q.negative else any(_overlaps(c, g) for c in valid for g in q.gold)
    spans = [c["end"] - c["start"] + 1 for c in valid]

    reasons: list[str] = []
    if not fact_pass:
        reasons.append("missing facts: " + ", ".join(missing))
    if hit is False:
        reasons.append("no citation overlaps the gold evidence")
    if not citations_ok:
        reasons.append(
            f"citation problems (valid={len(valid)}, invalid={n_invalid}, ungrounded={n_ungrounded})"
        )
    if payload.get("stopped") != "done":
        reasons.append(f"agent stopped early: {payload.get('stopped')}")
    passed = fact_pass and citations_ok and (hit is not False) and payload.get("stopped") == "done"
    return Score(
        passed, fact_pass, hit, citations_ok, len(valid), n_invalid, n_ungrounded,
        mean(spans) if spans else None, missing, reasons,
    )


def repeated_calls(trace: dict[str, Any]) -> int:
    """How many tool calls in a trace repeat an earlier one (searches compare by their words)."""
    seen: set[tuple] = set()
    repeats = 0
    for e in trace.get("events", []):
        if e.get("kind") != "tool_call":
            continue
        inp = e.get("input", {})
        if e["name"] == "search_code":
            key: tuple = (e["name"], tuple(sorted(set(re.findall(r"[a-z0-9]+", str(inp.get("query", "")).lower())))))
        else:
            key = (e["name"], json.dumps(inp, sort_keys=True, default=str))
        repeats += key in seen
        seen.add(key)
    return repeats


def wilson(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval. With a few dozen questions the interval matters as much as the rate."""
    if n == 0:
        return (0.0, 0.0)
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def percentile(values: list[float], q: float) -> float | None:
    """Nearest-rank percentile."""
    if not values:
        return None
    s = sorted(values)
    return s[max(0, min(len(s) - 1, math.ceil(q * len(s)) - 1))]


def _rate(num: int, den: int) -> float | None:
    return num / den if den else None


def aggregate(traces: list[dict[str, Any]], price_in: float | None = None, price_out: float | None = None) -> dict[str, Any]:
    """Summarise a run. Prices are dollars per million tokens and optional; without them cost is omitted."""
    n = len(traces)
    ok = [t for t in traces if not t.get("error")]
    scores = [t["score"] for t in traces]
    pos = [t for t in traces if not t["negative"]]
    neg = [t for t in traces if t["negative"]]
    passes = sum(s["passed"] for s in scores)
    valid = sum(s["n_valid"] for s in scores)
    invalid = sum(s["n_invalid"] for s in scores)
    ungrounded = sum(s["n_ungrounded"] for s in scores)
    lat = [t["latency_s"] for t in ok]
    toks_in = [t["payload"]["usage"]["input_tokens"] for t in ok]
    toks_out = [t["payload"]["usage"]["output_tokens"] for t in ok]
    spans = [s["avg_span"] for s in scores if s["avg_span"] is not None]

    def group(key: str) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for name in sorted({t[key] for t in traces}):
            sub = [t for t in traces if t[key] == name]
            out[name] = {"n": len(sub), "passed": sum(t["score"]["passed"] for t in sub)}
            out[name]["pass_rate"] = out[name]["passed"] / len(sub)
        return out

    summary: dict[str, Any] = {
        "n": n,
        "errors": n - len(ok),
        "passed": passes,
        "pass_rate": _rate(passes, n),
        "pass_ci95": wilson(passes, n),
        "fact_rate": _rate(sum(s["fact_pass"] for s in scores), n),
        "evidence_hit_rate": _rate(sum(1 for t in pos if t["score"]["evidence_hit"]), len(pos)),
        "negative_pass_rate": _rate(sum(t["score"]["passed"] for t in neg), len(neg)),
        "n_positive": len(pos),
        "n_negative": len(neg),
        "citations": {"valid": valid, "invalid": invalid, "ungrounded": ungrounded},
        "citation_validity": _rate(valid, valid + invalid),
        "grounded_rate": _rate(valid - ungrounded, valid),
        "strict_citation_ok_rate": _rate(sum(s["citations_ok"] for s in scores), n),
        "avg_cited_span_lines": mean(spans) if spans else None,
        "latency_p50_s": percentile(lat, 0.5),
        "latency_p95_s": percentile(lat, 0.95),
        "latency_mean_s": mean(lat) if lat else None,
        "steps_mean": mean(t["payload"]["steps"] for t in ok) if ok else None,
        "tokens_in_mean": mean(toks_in) if ok else None,
        "tokens_out_mean": mean(toks_out) if ok else None,
        "tokens_total": sum(toks_in) + sum(toks_out),
        "stopped": {k: sum(1 for t in ok if t["payload"]["stopped"] == k) for k in sorted({t["payload"]["stopped"] for t in ok})},
        "unfinished": sum(1 for t in ok if t["payload"]["stopped"] != "done"),
        "repeated_calls": sum(repeated_calls(t) for t in ok),
        "questions_with_repeats": sum(1 for t in ok if repeated_calls(t) > 0),
        "by_repo": group("repo"),
        "by_category": group("category"),
    }
    if price_in is not None and price_out is not None and ok:
        costs = [(a * price_in + b * price_out) / 1e6 for a, b in zip(toks_in, toks_out, strict=True)]
        summary["cost_per_query_usd"] = mean(costs)
        summary["cost_total_usd"] = sum(costs)
    return summary
