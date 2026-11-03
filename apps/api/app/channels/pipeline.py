"""One inbound pipeline for every channel: de-duplicate -> identify user -> commands or agent -> reply."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.approvals import service as approvals
from app.channels.base import Button, ChannelAdapter, InboundMessage
from app.channels.linking import find_identity, link_identity, parse_link_command
from app.channels.telegram import TelegramAdapter
from app.channels.whatsapp import WhatsAppAdapter
from app.core.errors import AppError
from app.core.logging import get_logger
from app.db import models as m
from app.db.session import get_session_factory

log = get_logger(__name__)

_adapters: dict[str, ChannelAdapter] = {"whatsapp": WhatsAppAdapter(), "telegram": TelegramAdapter()}

NOT_LINKED = (
    "Hi! I'm Life Easy, your job-search assistant. This chat isn't linked to an account yet.\n\n"
    "Open the Life Easy dashboard > Settings > Link messaging, then send me:\nLINK <your code>"
)
HELP = (
    "You can ask me things like:\n"
    "- find backend jobs in Bengaluru\n- show my matches\n- draft a follow-up for my Acme application\n"
    "- what interviews do I have this week?\n\nI never send anything on your behalf without your approval.\n"
    "Send STOP to unlink this chat."
)
OPT_OUT_WORDS = {"stop", "unsubscribe", "/stop", "unlink"}


def get_adapter(channel: str) -> ChannelAdapter:
    try:
        return _adapters[channel]
    except KeyError as exc:
        raise AppError(f"unknown channel {channel}") from exc


def set_adapter(channel: str, adapter: ChannelAdapter) -> None:
    """Tests swap in a recording adapter."""
    _adapters[channel] = adapter


async def _dedupe(session: AsyncSession, provider: str, event_id: str) -> bool:
    try:
        async with session.begin_nested():
            session.add(m.ProcessedEvent(provider=provider, event_id=event_id))
            await session.flush()
        return True
    except IntegrityError:
        return False


def approval_buttons(approval: m.ActionApproval) -> list[Button]:
    return [Button(id=f"approve:{approval.id.hex}", label="Approve"), Button(id=f"reject:{approval.id.hex}", label="Reject")]


async def _handle_command(session: AsyncSession, user_id: uuid.UUID, msg: InboundMessage) -> str | None:
    """Button ids and text commands that do not need the LLM. Returns the reply, or None if not a command."""
    from app.applications.service import create_application
    from app.resumes import service as resumes

    text = (msg.text or "").strip()
    action, _, arg = (msg.button_id or "").partition(":")
    if not action:
        lowered = text.lower()
        for verb in ("approve", "reject"):
            if lowered.startswith(verb + " "):
                action, arg = verb, lowered.split(None, 1)[1]
                break
        if lowered in ("help", "/help", "?"):
            return HELP
    if not action:
        return None
    if action in ("approve", "reject"):
        approval = await _resolve_approval(session, user_id, arg)
        if approval is None:
            return "I couldn't find a pending approval with that id. Send 'help' to see what I can do."
        if action == "approve":
            await approvals.approve(session, user_id, approval, expected_hash=None, via=msg.provider)
            return f"Approved #{approvals.short_id(approval)}. Sending now; I'll confirm when it's done."
        await approvals.reject(session, user_id, approval, via=msg.provider)
        return f"Rejected #{approvals.short_id(approval)}. Nothing was sent."
    if action in ("save", "skip", "tailor") and arg:
        try:
            job_id = uuid.UUID(arg)
        except ValueError:
            return None
        job = await session.get(m.Job, job_id)
        if job is None:
            return "That job is no longer available."
        jm = await session.get(m.JobMatch, {"user_id": user_id, "job_id": job_id})
        if jm is None:
            jm = m.JobMatch(user_id=user_id, job_id=job_id, score=0, explanation={})
            session.add(jm)
        if action == "save":
            jm.status = "saved"
            return f"Saved: {job.title} at {job.company}.\n{job.apply_url}"
        if action == "skip":
            jm.status = "skipped"
            return f"Skipped {job.title} at {job.company}. I'll show fewer like it."
        resume = await resumes.primary_resume(session, user_id)
        if resume is None:
            return "Upload a resume in the dashboard first, then I can tailor it."
        tailored, ats = await resumes.tailor(session, user_id, job=job, resume=resume, notes=None)
        missing = ", ".join(ats.get("missing_keywords", [])[:6]) or "none"
        return f"Tailored resume ready for {job.title} at {job.company} (ATS score {ats.get('score', '?')}/100; missing keywords: {missing}). Download it from the dashboard > Resumes."
    if action == "applied" and arg:
        job = await session.get(m.Job, uuid.UUID(arg))
        if job is None:
            return "That job is no longer available."
        await create_application(session, user_id, job=job, status="applied", source=msg.provider)
        jm = await session.get(m.JobMatch, {"user_id": user_id, "job_id": job.id})
        if jm is not None:
            jm.status = "applied"
        return f"Marked as applied: {job.title} at {job.company}. I'll remind you to follow up in 7 days."
    return None


async def _resolve_approval(session: AsyncSession, user_id: uuid.UUID, ref: str) -> m.ActionApproval | None:
    ref = (ref or "").strip().replace("#", "")
    try:
        approval = await session.get(m.ActionApproval, uuid.UUID(ref))
        return approval if approval is not None and approval.user_id == user_id else None
    except ValueError:
        return await approvals.find_by_prefix(session, user_id, ref)


async def handle_inbound(
    *,
    channel: str,
    external_id: str,
    text: str,
    event_id: str,
    display_name: str | None = None,
    reply_to: dict[str, Any] | None = None,
    button_id: str | None = None,
) -> dict[str, Any]:
    adapter = get_adapter(channel)
    msg = InboundMessage(
        provider=channel,
        external_id=external_id,
        text=text,
        event_id=event_id,
        display_name=display_name,
        button_id=button_id,
        reply_to=reply_to or {},
    )
    async with get_session_factory()() as session:
        if not await _dedupe(session, channel, event_id):
            await session.commit()
            return {"status": "duplicate"}
        await adapter.acknowledge(msg)
        identity = await find_identity(session, channel, external_id)
        if identity is None:
            code = parse_link_command(text)
            if code:
                try:
                    identity = await link_identity(
                        session, provider=channel, external_id=external_id, code=code, display_name=display_name
                    )
                    await session.commit()
                    await adapter.send_text(
                        external_id, "Linked! This chat is now connected to your Life Easy account.\n\n" + HELP
                    )
                    return {"status": "linked", "user_id": str(identity.user_id)}
                except AppError as exc:
                    await session.commit()
                    await adapter.send_text(external_id, exc.message)
                    return {"status": "link_failed"}
            await session.commit()
            await adapter.send_text(external_id, NOT_LINKED)
            return {"status": "not_linked"}
        user = await session.get(m.User, identity.user_id)
        if user is None or not user.is_active or user.deleted_at is not None:
            await session.commit()
            await adapter.send_text(external_id, "This account is no longer active.")
            return {"status": "inactive"}
        if (text or "").strip().lower() in OPT_OUT_WORDS:
            # Opt-out: unlink this chat at once; no more proactive messages go here.
            from datetime import UTC, datetime

            identity.revoked_at = datetime.now(UTC)
            await session.commit()
            await adapter.send_text(
                external_id,
                "Done - this chat is unlinked and I won't message you here again. Link it again any time from the dashboard.",
            )
            return {"status": "opted_out"}
        try:
            reply = await _handle_command(session, user.id, msg)
            if reply is not None:
                await session.commit()
                await adapter.send_text(external_id, reply)
                return {"status": "command"}
            if not text.strip():
                await session.commit()
                return {"status": "empty"}
            from app.agent.agent import run as run_agent

            result = await run_agent(session, user, text, channel=channel)
            await session.commit()
        except AppError as exc:
            await session.rollback()
            await adapter.send_text(external_id, f"Sorry, I couldn't do that: {exc.message}")
            return {"status": "error", "error": exc.code}
        if result.reply:
            await adapter.send_text(external_id, result.reply)
        for approval in result.approvals:
            await adapter.send_buttons(external_id, approvals.preview_text(approval), approval_buttons(approval))
        return {"status": "replied", "approvals": len(result.approvals), "tools": result.tool_calls}
