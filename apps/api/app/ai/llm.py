"""LLM provider abstraction.

Business logic talks to `LLM.complete()` / `LLM.json()` only, so the vendor can
change without touching agents. `AnthropicLLM` is the production provider;
`FakeLLM` is deterministic for tests and for running the stack without a key.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.config import get_settings
from app.core.errors import ProviderError


@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict[str, Any]


@dataclass
class LLMResponse:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_reason: str = "end_turn"
    tokens_in: int = 0
    tokens_out: int = 0


class LLM:
    name = "base"

    async def complete(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[ToolSpec] | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.3,
    ) -> LLMResponse:
        raise NotImplementedError

    async def json(self, *, system: str, prompt: str, schema: dict[str, Any], max_tokens: int = 1024) -> dict[str, Any]:
        """Return a JSON object that matches `schema` (JSON Schema, type=object)."""
        raise NotImplementedError


class AnthropicLLM(LLM):
    name = "anthropic"

    def __init__(self, api_key: str, model: str) -> None:
        from anthropic import AsyncAnthropic

        self._client = AsyncAnthropic(api_key=api_key)
        self._model = model

    async def complete(self, *, system, messages, tools=None, max_tokens=1024, temperature=0.3):  # type: ignore[no-untyped-def]
        kwargs: dict[str, Any] = {
            "model": self._model,
            "system": system,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if tools:
            kwargs["tools"] = [{"name": t.name, "description": t.description, "input_schema": t.input_schema} for t in tools]
        try:
            resp = await self._client.messages.create(**kwargs)
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(f"LLM request failed: {type(exc).__name__}") from exc
        out = LLMResponse(stop_reason=resp.stop_reason or "end_turn")
        for block in resp.content:
            if block.type == "text":
                out.text += block.text
            elif block.type == "tool_use":
                out.tool_calls.append(ToolCall(id=block.id, name=block.name, input=dict(block.input or {})))
        if resp.usage:
            out.tokens_in = resp.usage.input_tokens
            out.tokens_out = resp.usage.output_tokens
        return out

    async def json(self, *, system, prompt, schema, max_tokens=1024):  # type: ignore[no-untyped-def]
        try:
            resp = await self._client.messages.create(
                model=self._model,
                system=system,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=0.0,
                tools=[{"name": "emit", "description": "Return the structured result.", "input_schema": schema}],
                tool_choice={"type": "tool", "name": "emit"},
            )
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(f"LLM request failed: {type(exc).__name__}") from exc
        for block in resp.content:
            if block.type == "tool_use":
                return dict(block.input or {})
        raise ProviderError("LLM returned no structured output")


def _default_for(schema: dict[str, Any]) -> Any:
    t = schema.get("type")
    if "default" in schema:
        return schema["default"]
    if t == "object":
        return {k: _default_for(v) for k, v in schema.get("properties", {}).items()}
    if t == "array":
        return []
    if t == "string":
        return schema.get("enum", [""])[0]
    if t in ("number", "integer"):
        return 0
    if t == "boolean":
        return False
    return None


class FakeLLM(LLM):
    """Deterministic stand-in. Tests pass handlers; the default echoes and fills schemas with defaults."""

    name = "fake"

    def __init__(
        self,
        complete_handler: Callable[[str, list[dict[str, Any]], list[ToolSpec] | None], LLMResponse] | None = None,
        json_handler: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
    ) -> None:
        self.complete_handler = complete_handler
        self.json_handler = json_handler
        self.calls: list[dict[str, Any]] = []

    async def complete(self, *, system, messages, tools=None, max_tokens=1024, temperature=0.3):  # type: ignore[no-untyped-def]
        self.calls.append({"kind": "complete", "system": system, "messages": messages, "tools": tools})
        if self.complete_handler:
            return self.complete_handler(system, messages, tools)
        last = messages[-1]["content"] if messages else ""
        if isinstance(last, list):
            last = " ".join(b.get("text", "") for b in last if isinstance(b, dict))
        return LLMResponse(text=f"[fake-llm] I read: {str(last)[:200]}")

    async def json(self, *, system, prompt, schema, max_tokens=1024):  # type: ignore[no-untyped-def]
        self.calls.append({"kind": "json", "system": system, "prompt": prompt, "schema": schema})
        if self.json_handler:
            return self.json_handler(prompt, schema)
        return _default_for(schema)


_llm: LLM | None = None


def get_llm() -> LLM:
    global _llm
    if _llm is None:
        settings = get_settings()
        if settings.llm_provider == "anthropic":
            if not settings.anthropic_api_key:
                raise ProviderError("ANTHROPIC_API_KEY is not set")
            _llm = AnthropicLLM(settings.anthropic_api_key, settings.anthropic_model)
        else:
            _llm = FakeLLM()
    return _llm


def set_llm(llm: LLM | None) -> None:
    """Tests inject a scripted FakeLLM."""
    global _llm
    _llm = llm


def untrusted(text: str, source: str) -> str:
    """Wrap third-party text so the model treats it as data, never as instructions."""
    safe = (text or "").replace("</untrusted_content>", "</untrusted_content >")
    return f'<untrusted_content source="{source}">\n{safe}\n</untrusted_content>'


def dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)
