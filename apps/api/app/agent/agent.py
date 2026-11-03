"""The conversation loop: context -> LLM with tools -> execute safe tools -> reply."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent import tools
from app.agent.memory import recall
from app.agent.prompts import build_system
from app.ai.llm import dumps, get_llm
from app.ai.usage import charge, ensure_within_limit
from app.core.errors import AppError
from app.core.logging import get_logger
from app.db import models as m

log = get_logger(__name__)
MAX_TOOL_ROUNDS = 6
HISTORY_MESSAGES = 16


@dataclass
class AgentResult:
    reply: str
    approvals: list[m.ActionApproval] = field(default_factory=list)
    tool_calls: list[str] = field(default_factory=list)


async def get_conversation(session: AsyncSession, user_id, channel: str) -> m.Conversation:  # type: ignore[no-untyped-def]
    conv = await session.scalar(
        select(m.Conversation)
        .where(m.Conversation.user_id == user_id, m.Conversation.channel == channel)
        .order_by(m.Conversation.created_at.desc())
        .limit(1)
    )
    if conv is None:
        conv = m.Conversation(user_id=user_id, channel=channel)
        session.add(conv)
        await session.flush()
    return conv


async def _history(session: AsyncSession, conv: m.Conversation) -> list[dict[str, Any]]:
    rows = (
        await session.scalars(
            select(m.Message)
            .where(m.Message.conversation_id == conv.id)
            .order_by(m.Message.created_at.desc())
            .limit(HISTORY_MESSAGES)
        )
    ).all()
    messages: list[dict[str, Any]] = []
    for row in reversed(rows):
        if row.role in ("user", "assistant") and row.content.strip():
            if messages and messages[-1]["role"] == row.role:
                messages[-1]["content"] += "\n" + row.content
            else:
                messages.append({"role": row.role, "content": row.content})
    if messages and messages[0]["role"] == "assistant":
        messages.pop(0)
    return messages


async def _store(
    session: AsyncSession, conv: m.Conversation, user_id, role: str, content: str, meta: dict[str, Any] | None = None
) -> None:  # type: ignore[no-untyped-def]
    from datetime import UTC, datetime, timedelta

    # Strictly increasing per conversation: coarse clocks (Windows ~15 ms) would otherwise give a
    # question and its answer the same timestamp and history could come back out of order.
    now = datetime.now(UTC)
    if conv.last_message_at is not None and now <= conv.last_message_at:
        now = conv.last_message_at + timedelta(microseconds=1)
    session.add(
        m.Message(conversation_id=conv.id, user_id=user_id, role=role, content=content[:20000], meta=meta or {}, created_at=now)
    )
    conv.last_message_at = now
    await session.flush()


async def run(session: AsyncSession, user: m.User, text: str, *, channel: str) -> AgentResult:
    await ensure_within_limit(session, user.id)
    conv = await get_conversation(session, user.id, channel)
    history = await _history(session, conv)
    await _store(session, conv, user.id, "user", text)
    profile = await session.get(m.Profile, user.id)
    memories = await recall(session, user.id, text)
    system = build_system(user, profile, memories, channel=channel)
    messages: list[dict[str, Any]] = [*history, {"role": "user", "content": text}]
    if messages and messages[0]["role"] != "user":
        messages = messages[1:]
    ctx = tools.ToolContext(session=session, user=user, channel=channel)
    llm = get_llm()
    reply = ""
    for _ in range(MAX_TOOL_ROUNDS):
        resp = await llm.complete(system=system, messages=messages, tools=tools.specs(), max_tokens=1200)
        await charge(session, user.id, "llm", tokens_in=resp.tokens_in, tokens_out=resp.tokens_out)
        if not resp.tool_calls:
            reply = resp.text.strip()
            break
        content: list[dict[str, Any]] = []
        if resp.text.strip():
            content.append({"type": "text", "text": resp.text})
        content += [{"type": "tool_use", "id": c.id, "name": c.name, "input": c.input} for c in resp.tool_calls]
        messages.append({"role": "assistant", "content": content})
        results: list[dict[str, Any]] = []
        for call in resp.tool_calls:
            ctx_result = await _run_tool(ctx, call.name, call.input)
            results.append({"type": "tool_result", "tool_use_id": call.id, "content": dumps(ctx_result)})
        messages.append({"role": "user", "content": results})
        if resp.text.strip():
            reply = resp.text.strip()
    else:
        reply = reply or "I did several steps but ran out of room; ask me to continue."
    if not reply:
        reply = "Done." if ctx.tool_calls_made else "I'm not sure what to do with that. Try 'help'."
    await _store(
        session,
        conv,
        user.id,
        "assistant",
        reply,
        {"tools": ctx.tool_calls_made, "approvals": [str(a.id) for a in ctx.approvals]},
    )
    return AgentResult(reply=reply, approvals=list(ctx.approvals), tool_calls=list(ctx.tool_calls_made))


async def _run_tool(ctx: tools.ToolContext, name: str, args: dict[str, Any]) -> Any:
    fn = tools.handler(name)
    ctx.tool_calls_made.append(name)
    if fn is None:
        return {"error": f"unknown tool {name}"}
    try:
        async with ctx.session.begin_nested():
            return await fn(ctx, args or {})
    except AppError as exc:
        return {"error": exc.message}
    except (ValueError, KeyError, TypeError) as exc:
        return {"error": f"bad arguments: {exc}"}
    except Exception as exc:  # noqa: BLE001
        log.exception("tool failed", tool=name)
        return {"error": f"{name} failed: {type(exc).__name__}"}


def tool_result_text(result: Any) -> str:
    return json.dumps(result, ensure_ascii=False, default=str)
