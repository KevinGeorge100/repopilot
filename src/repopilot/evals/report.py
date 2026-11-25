"""Render a run as markdown, optionally compared with a baseline run."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .metrics import aggregate
from .runner import read_traces


def load_run(run_dir: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    traces = read_traces(run_dir / "traces.jsonl")
    cfg_path = run_dir / "config.json"
    return traces, (json.loads(cfg_path.read_text()) if cfg_path.exists() else {})


def pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x * 100:.0f}%"


def num(x: float | None, digits: int = 1) -> str:
    return "n/a" if x is None else f"{x:,.{digits}f}"


def _delta(a: float | None, b: float | None, pct_mode: bool, lower_is_better: bool = False) -> str:
    if a is None or b is None:
        return ""
    d = (b - a) * (100 if pct_mode else 1)
    if abs(d) < (0.5 if pct_mode else 0.05):
        return "no change"
    better = (d < 0) == lower_is_better
    return f"{d:+.0f} pts" + (" (better)" if better else " (worse)") if pct_mode else f"{d:+.1f}" + (" (better)" if better else " (worse)")


def render_markdown(
    traces: list[dict[str, Any]],
    config: dict[str, Any],
    price_in: float | None = None,
    price_out: float | None = None,
    baseline: tuple[list[dict[str, Any]], dict[str, Any]] | None = None,
) -> str:
    s = aggregate(traces, price_in, price_out)
    s_all_n = s["n"]
    cfg = config.get("config", {})
    lo, hi = s["pass_ci95"]
    out = [f"# Evaluation: {cfg.get('label', 'run')}", ""]
    out.append(
        f"Provider `{cfg.get('provider') or 'default'}`, model `{cfg.get('model') or 'default'}`, search k={cfg.get('search_k')}, "
        f"tool result cap {cfg.get('max_result_chars')} chars, max steps {cfg.get('max_steps')}. "
        f"{s['n']} questions ({s['n_positive']} positive, {s['n_negative']} where the right answer is \"not in this repo\")."
    )
    scoring = (
        "Scoring is deterministic, not an LLM judge. A question passes when every expected fact matches the answer, "
        "a verified citation overlaps the gold evidence lines, and no citation is invalid or unread by the agent."
    )
    out += ["", scoring, ""]

    out += ["## Headline", "", "| Metric | Value |", "|---|---|"]
    out.append(f"| Questions passed | {s['passed']}/{s['n']} = **{pct(s['pass_rate'])}** (95% CI {pct(lo)} to {pct(hi)}) |")
    out.append(f"| Expected facts present | {pct(s['fact_rate'])} |")
    out.append(f"| Citation hits the gold evidence (positive questions) | {pct(s['evidence_hit_rate'])} |")
    out.append(f"| Negative questions answered correctly | {pct(s['negative_pass_rate'])} |")
    c = s["citations"]
    out.append(f"| Citation validity | {pct(s['citation_validity'])} ({c['valid']} valid, {c['invalid']} invalid) |")
    out.append(f"| Citations the agent had actually read | {pct(s['grounded_rate'])} ({c['ungrounded']} unread) |")
    out.append(f"| Average cited span | {num(s['avg_cited_span_lines'])} lines |")
    out.append(f"| Latency p50 / p95 | {num(s['latency_p50_s'])}s / {num(s['latency_p95_s'])}s |")
    out.append(f"| Steps per question | {num(s['steps_mean'])} |")
    out.append(f"| Ran out of steps or tokens with no finished answer | {s['unfinished']} of {s['n']} |")
    out.append(f"| Repeated tool calls | {s['repeated_calls']} (in {s['questions_with_repeats']} questions) |")
    out.append(f"| Tokens per question (in / out) | {num(s['tokens_in_mean'], 0)} / {num(s['tokens_out_mean'], 0)} |")
    if "cost_per_query_usd" in s:
        out.append(f"| Cost per question | ${s['cost_per_query_usd']:.4f} at ${price_in}/M in, ${price_out}/M out |")
    if s["errors"]:
        answered_n = s["n"] - s["errors"]
        ok_pass = sum(1 for t in traces if not t.get("error") and t["score"]["passed"])
        out.append(f"| Provider errors (not counted against the agent below) | {s['errors']} |")
        out.append(f"| Passed among the {answered_n} answered questions | {ok_pass}/{answered_n} = {pct(ok_pass / answered_n if answered_n else None)} |")
    out.append("")

    out += ["## By repo", "", "| Repo | Passed |", "|---|---|"]
    out += [f"| {k} | {v['passed']}/{v['n']} ({pct(v['pass_rate'])}) |" for k, v in s["by_repo"].items()]
    out += ["", "## By question type", "", "| Type | Passed |", "|---|---|"]
    out += [f"| {k} | {v['passed']}/{v['n']} ({pct(v['pass_rate'])}) |" for k, v in s["by_category"].items()]

    stats = config.get("index_stats") or {}
    if stats:
        out += ["", "## Indexing", "", "| Repo | Chunks | Time |", "|---|---|---|"]
        out += [f"| {k} | {v['chunks']} | {v['index_seconds']:.0f}s |" for k, v in stats.items()]

    fails = [t for t in traces if not t["score"]["passed"]]
    out += ["", f"## Failures ({len(fails)})", ""]
    out += [f"- `{t['id']}` ({t['category']}): {'; '.join(t['score']['reasons'])}" for t in fails] or ["None."]

    if baseline:
        b_all, b_cfg = baseline
        # A provider failure (quota, outage) says nothing about the agent. Compare only the questions that
        # both runs actually answered, so one run's missing answers are not scored as the other's gains.
        answered = {t["id"] for t in traces if not t.get("error")} & {t["id"] for t in b_all if not t.get("error")}
        b_traces = [t for t in b_all if t["id"] in answered]
        traces = [t for t in traces if t["id"] in answered]
        s = aggregate(traces, price_in, price_out)
        b = aggregate(b_traces, price_in, price_out)
        bl = b_cfg.get("config", {}).get("label", "baseline")
        out += ["", f"## Change from `{bl}` to `{cfg.get('label', 'run')}`", ""]
        if len(answered) < s_all_n:
            skipped = s_all_n - len(answered)
            note = (
                f"Compared on the {len(answered)} questions both runs answered; the other {skipped} hit a provider error "
                "in one of the runs and are left out of both sides."
            )
            out += [note, ""]
        out += ["| Metric | Before | After | Change |", "|---|---|---|---|"]
        rows = [("Questions passed", "pass_rate", True, False), ("Expected facts present", "fact_rate", True, False),
                ("Citation hits gold evidence", "evidence_hit_rate", True, False), ("Citation validity", "citation_validity", True, False),
                ("Negative questions correct", "negative_pass_rate", True, False)]
        for name, key, pm, low in rows:
            out.append(f"| {name} | {pct(b[key])} | {pct(s[key])} | {_delta(b[key], s[key], pm, low)} |")
        for name, key, low in [("Latency p50 (s)", "latency_p50_s", True), ("Steps per question", "steps_mean", True),
                               ("Tokens in per question", "tokens_in_mean", True), ("Average cited span (lines)", "avg_cited_span_lines", True),
                               ("Questions that ended with no answer", "unfinished", True), ("Repeated tool calls", "repeated_calls", True)]:
            d = 0 if key in ("tokens_in_mean", "unfinished", "repeated_calls") else 1
            out.append(f"| {name} | {num(b[key], d)} | {num(s[key], d)} | {_delta(b[key], s[key], False, low)} |")
        before = {t["id"]: t["score"]["passed"] for t in b_traces}
        after = {t["id"]: t["score"]["passed"] for t in traces}
        fixed = sorted(i for i in after if after[i] and before.get(i) is False)
        broke = sorted(i for i in after if not after[i] and before.get(i) is True)
        out += ["", f"Fixed: {', '.join(fixed) or 'none'}. Regressed: {', '.join(broke) or 'none'}."]
        n_changed = len(fixed) + len(broke)
        out += [f"Only {n_changed} of {len(after)} questions changed outcome, so treat small differences as noise.", ""]
    return "\n".join(out) + "\n"
