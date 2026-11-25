"""LLM abstraction: a tiny normalised interface, a scripted stub, and the Anthropic client."""
from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

DEFAULT_MODEL = "claude-sonnet-5-5"
log = logging.getLogger("repopilot.llm")


@dataclass
class TextBlock:
    text: str
    type: str = "text"


@dataclass
class ToolUse:
    id: str
    name: str
    input: dict[str, Any]
    type: str = "tool_use"
    extra: dict[str, Any] | None = None  # provider-specific passthrough (e.g. Gemini thought_signature)


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0


@dataclass
class LLMResponse:
    content: list[TextBlock | ToolUse]
    stop_reason: str = "end_turn"
    usage: Usage = field(default_factory=Usage)


class LLM(Protocol):
    def create(self, system: str, messages: list[dict], tools: list[dict]) -> LLMResponse: ...


def block_to_param(b: TextBlock | ToolUse) -> dict:
    if isinstance(b, TextBlock):
        return {"type": "text", "text": b.text}
    param = {"type": "tool_use", "id": b.id, "name": b.name, "input": b.input}
    if b.extra:
        param["extra_content"] = b.extra
    return param


class StubLLM:
    """Replays scripted responses and records every call, for deterministic tests."""

    def __init__(self, script: list[LLMResponse]) -> None:
        self.script = list(script)
        self.calls: list[dict] = []

    def create(self, system: str, messages: list[dict], tools: list[dict]) -> LLMResponse:
        self.calls.append({"system": system, "messages": list(messages), "tools": tools})
        if not self.script:
            raise RuntimeError("StubLLM script exhausted")
        return self.script.pop(0)


class AnthropicLLM:
    """Real client. Marks system + tool definitions cacheable (prompt caching)."""

    def __init__(self, model: str = DEFAULT_MODEL, max_tokens: int = 2048) -> None:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError("ANTHROPIC_API_KEY is not set")
        import anthropic

        self.client = anthropic.Anthropic()
        self.model = model
        self.max_tokens = max_tokens

    def create(self, system: str, messages: list[dict], tools: list[dict]) -> LLMResponse:
        cached_tools = [dict(t) for t in tools]
        if cached_tools:
            cached_tools[-1]["cache_control"] = {"type": "ephemeral"}
        kwargs: dict[str, Any] = {}
        if cached_tools:  # an empty tool list is how the agent forces a final answer; the API rejects an empty array
            kwargs["tools"] = cached_tools
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=messages,
            **kwargs,
        )
        blocks: list[TextBlock | ToolUse] = []
        for b in resp.content:
            if b.type == "text":
                blocks.append(TextBlock(b.text))
            elif b.type == "tool_use":
                blocks.append(ToolUse(b.id, b.name, dict(b.input)))
        u = resp.usage
        return LLMResponse(
            blocks,
            resp.stop_reason or "end_turn",
            Usage(u.input_tokens, u.output_tokens, getattr(u, "cache_read_input_tokens", 0) or 0),
        )


# ---------------------------------------------------------------------------
# OpenAI-compatible providers (Gemini, Groq, OpenRouter): free-tier friendly.
# ---------------------------------------------------------------------------
PROVIDERS: dict[str, dict[str, str | None]] = {
    "anthropic": {"key_env": "ANTHROPIC_API_KEY", "base_url": None, "model": DEFAULT_MODEL},
    "gemini": {
        "key_env": "GEMINI_API_KEY",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "model": "gemini-3.5-flash-lite",  # the model the evaluation measured; 3.1-flash-lite returned 503s under load
    },
    "groq": {"key_env": "GROQ_API_KEY", "base_url": "https://api.groq.com/openai/v1", "model": "openai/gpt-oss-120b"},
    "openrouter": {"key_env": "OPENROUTER_API_KEY", "base_url": "https://openrouter.ai/api/v1", "model": None},
}


def to_openai_messages(system: str, messages: list[dict]) -> list[dict]:
    """Convert our Anthropic-style transcript into OpenAI chat messages."""
    out: list[dict] = [{"role": "system", "content": system}]
    for m in messages:
        content = m["content"]
        if isinstance(content, str):
            out.append({"role": m["role"], "content": content})
        elif m["role"] == "assistant":
            text = "".join(b["text"] for b in content if b["type"] == "text")
            calls = []
            for b in content:
                if b["type"] != "tool_use":
                    continue
                call = {"id": b["id"], "type": "function", "function": {"name": b["name"], "arguments": json.dumps(b["input"])}}
                if b.get("extra_content"):
                    call["extra_content"] = b["extra_content"]
                calls.append(call)
            msg: dict = {"role": "assistant", "content": text or None}
            if calls:
                msg["tool_calls"] = calls
            out.append(msg)
        else:  # user turn made of tool_result blocks (and/or text)
            for b in content:
                if b["type"] == "tool_result":
                    out.append({"role": "tool", "tool_call_id": b["tool_use_id"], "content": b["content"]})
                elif b["type"] == "text":
                    out.append({"role": "user", "content": b["text"]})
    return out


def to_openai_tools(tools: list[dict]) -> list[dict]:
    return [
        {"type": "function", "function": {"name": t["name"], "description": t["description"], "parameters": t["input_schema"]}}
        for t in tools
    ]


class OpenAICompatLLM:
    """Chat-completions client over plain httpx, with 429/5xx retry (free tiers rate-limit hard)."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        max_tokens: int = 4096,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        max_retries: int = 4,
    ) -> None:
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.model, self.max_tokens, self.sleep, self.max_retries = model, max_tokens, sleep, max_retries
        self.client = client or httpx.Client(timeout=120)
        self.headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    def create(self, system: str, messages: list[dict], tools: list[dict]) -> LLMResponse:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": to_openai_messages(system, messages),
            "max_tokens": self.max_tokens,
        }
        if tools:  # no tools means "answer in text now"; some providers reject an empty array
            body["tools"] = to_openai_tools(tools)
        for attempt in range(self.max_retries + 1):
            t0 = time.monotonic()
            try:
                r = self.client.post(self.url, headers=self.headers, json=body)
            except httpx.HTTPError as e:
                log.warning("llm network error %s after %.1fs (attempt %d)", type(e).__name__, time.monotonic() - t0, attempt + 1)
                if attempt < self.max_retries:
                    self.sleep(min(2.0**attempt, 30.0))
                    continue
                raise RuntimeError(f"LLM provider unreachable: {type(e).__name__}") from e
            log.info("llm %s status=%s %.1fs", self.model, r.status_code, time.monotonic() - t0)
            if r.status_code in (429, 500, 502, 503) and attempt < self.max_retries:
                try:
                    wait = float(r.headers.get("retry-after", ""))
                except ValueError:
                    wait = 2.0**attempt
                self.sleep(min(wait, 60.0))
                continue
            if r.status_code >= 400:
                raise RuntimeError(f"LLM provider error {r.status_code}: {r.text[:300]}")
            break
        data = r.json()
        msg = data["choices"][0]["message"]
        blocks: list[TextBlock | ToolUse] = []
        if msg.get("content"):
            blocks.append(TextBlock(msg["content"]))
        for tc in msg.get("tool_calls") or []:
            try:
                args = json.loads(tc["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            blocks.append(
                ToolUse(tc["id"], tc["function"]["name"], args if isinstance(args, dict) else {}, extra=tc.get("extra_content"))
            )
        u = data.get("usage") or {}
        has_tools = any(isinstance(b, ToolUse) for b in blocks)
        return LLMResponse(
            blocks, "tool_use" if has_tools else "end_turn", Usage(u.get("prompt_tokens", 0), u.get("completion_tokens", 0))
        )


def make_llm(provider: str | None = None, model: str | None = None) -> LLM:
    """Pick a backend from args or env: REPOPILOT_PROVIDER / REPOPILOT_MODEL."""
    provider = (provider or os.environ.get("REPOPILOT_PROVIDER") or "anthropic").lower()
    if provider not in PROVIDERS:
        raise RuntimeError(f"unknown provider '{provider}' (choose: {', '.join(PROVIDERS)})")
    cfg = PROVIDERS[provider]
    model = model or os.environ.get("REPOPILOT_MODEL") or cfg["model"]
    if provider == "anthropic":
        return AnthropicLLM(model or DEFAULT_MODEL)
    key = os.environ.get(str(cfg["key_env"]))
    if not key:
        raise RuntimeError(f"{cfg['key_env']} is not set")
    if not model:
        raise RuntimeError(f"set REPOPILOT_MODEL (or --model) for provider '{provider}'")
    return OpenAICompatLLM(str(cfg["base_url"]), key, model)
