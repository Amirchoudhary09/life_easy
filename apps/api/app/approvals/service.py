"""The approval gate for every outbound action.

Rules (docs/architecture.md):
- the preview shows channel, exact destination, full body and attachments;
- approval binds to `content_hash` of those fields; an edit creates a new row;
- a worker executes once, with the approval id as the idempotency key, and
  writes an audit event with the result.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.audit import record_audit
from app.core.errors import AppError, Conflict, NotFound
from app.core.logging import get_logger
from app.db import models as m
from app.db.session import get_session_factory
from app.tasks.runner import enqueue

log = get_logger(__name__)

Executor = Callable[[AsyncSession, m.ActionApproval], Awaitable[dict[str, Any]]]
_executors: dict[str, Executor] = {}

ACTION_LABELS = {
    "send_email": "Email",
    "linkedin_post": "LinkedIn post",
    "linkedin_message": "LinkedIn message",
    "submit_application": "Job application",
}


def register_executor(action_type: str) -> Callable[[Executor], Executor]:
    def deco(fn: Executor) -> Executor:
        _executors[action_type] = fn
        return fn

    return deco


def compute_hash(
    *,
    action_type: str,
    channel: str,
    destination: dict[str, Any],
    subject: str | None,
    body: str,
    attachments: list[dict[str, Any]],
) -> str:
    canonical = json.dumps(
        {
            "action_type": action_type,
            "channel": channel,
            "destination": destination,
            "subject": subject or "",
            "body": body,
            "attachments": attachments,
        },
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def create_approval(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    action_type: str,
    channel: str,
    destination: dict[str, Any],
    subject: str | None,
    body: str,
    attachments: list[dict[str, Any]] | None = None,
    payload: dict[str, Any] | None = None,
    preview_channel: str | None = None,
    related_application_id: uuid.UUID | None = None,
    actor: str = "agent",
) -> m.ActionApproval:
    if not body.strip():
        raise AppError("cannot create an approval with an empty message")
    attachments = attachments or []
    content_hash = compute_hash(
        action_type=action_type, channel=channel, destination=destination, subject=subject, body=body, attachments=attachments
    )
    pending = await session.scalar(
        select(m.ActionApproval).where(
            m.ActionApproval.user_id == user_id,
            m.ActionApproval.content_hash == content_hash,
            m.ActionApproval.status == "pending",
        )
    )
    if pending is not None:
        return pending  # same content already waiting: do not create a duplicate
    approval = m.ActionApproval(
        user_id=user_id,
        action_type=action_type,
        channel=channel,
        destination=destination,
        subject=subject,
        body=body,
        attachments=attachments,
        payload=payload or {},
        content_hash=content_hash,
        idempotency_key=f"{user_id.hex[:8]}:{content_hash[:24]}:{secrets.token_hex(4)}",
        status="pending",
        preview_channel=preview_channel,
        expires_at=datetime.now(UTC) + timedelta(hours=get_settings().approval_ttl_hours),
        related_application_id=related_application_id,
    )
    session.add(approval)
    await session.flush()
    await record_audit(
        session,
        user_id=user_id,
        actor=actor,
        event_type="approval.create",
        target_type="approval",
        target_id=approval.id,
        details={"action_type": action_type, "channel": channel, "content_hash": content_hash},
    )
    return approval


async def get_owned(session: AsyncSession, user_id: uuid.UUID, approval_id: uuid.UUID) -> m.ActionApproval:
    approval = await session.get(m.ActionApproval, approval_id)
    if approval is None or approval.user_id != user_id:
        raise NotFound("approval not found")
    return approval


async def find_by_prefix(session: AsyncSession, user_id: uuid.UUID, prefix: str) -> m.ActionApproval | None:
    """Chat channels reference approvals by the first characters of the id."""
    prefix = prefix.strip().lower().replace("-", "")
    if len(prefix) < 4:
        return None
    rows = (
        await session.scalars(
            select(m.ActionApproval).where(m.ActionApproval.user_id == user_id, m.ActionApproval.status == "pending")
        )
    ).all()
    matches = [r for r in rows if r.id.hex.startswith(prefix)]
    return matches[0] if len(matches) == 1 else None


def short_id(approval: m.ActionApproval) -> str:
    return approval.id.hex[:8]


def preview_text(approval: m.ActionApproval) -> str:
    label = ACTION_LABELS.get(approval.action_type, approval.action_type)
    dest = approval.destination or {}
    lines = [f"{label} - waiting for your approval (#{short_id(approval)})", f"Channel: {approval.channel}"]
    if dest.get("to"):
        lines.append("To: " + ", ".join(dest["to"]))
    if dest.get("cc"):
        lines.append("Cc: " + ", ".join(dest["cc"]))
    if dest.get("audience"):
        lines.append(f"Audience: {dest['audience']}")
    if dest.get("recipient"):
        lines.append(f"Recipient: {dest['recipient']}")
    if approval.subject:
        lines.append(f"Subject: {approval.subject}")
    lines.append("")
    lines.append(approval.body)
    if approval.attachments:
        lines.append("")
        lines.append("Attachments: " + ", ".join(str(a.get("filename", a.get("type", "file"))) for a in approval.attachments))
    lines.append("")
    lines.append(
        f"Reply APPROVE {short_id(approval)} to send exactly this, or REJECT {short_id(approval)} to cancel. "
        "Any edit needs a new approval."
    )
    return "\n".join(lines)


def _check_pending(approval: m.ActionApproval) -> None:
    if approval.status != "pending":
        raise Conflict(f"approval is {approval.status}, not pending")
    if approval.expires_at < datetime.now(UTC):
        approval.status = "expired"
        raise Conflict("approval has expired; ask for a new preview")


async def approve(
    session: AsyncSession, user_id: uuid.UUID, approval: m.ActionApproval, *, expected_hash: str | None, via: str
) -> m.ActionApproval:
    """Mark approved and queue execution. `expected_hash` must match when the client previews content itself."""
    if approval.user_id != user_id:
        raise NotFound("approval not found")
    _check_pending(approval)
    if expected_hash is not None and expected_hash != approval.content_hash:
        raise Conflict("the content changed since the preview; review the new preview and approve again")
    approval.status = "approved"
    approval.approved_at = datetime.now(UTC)
    await record_audit(
        session,
        user_id=user_id,
        actor="user",
        event_type="approval.approve",
        target_type="approval",
        target_id=approval.id,
        details={"via": via, "content_hash": approval.content_hash},
    )
    await session.commit()
    await enqueue("execute_approval", approval_id=str(approval.id))
    await session.refresh(approval)
    return approval


async def reject(
    session: AsyncSession, user_id: uuid.UUID, approval: m.ActionApproval, *, via: str, reason: str | None = None
) -> m.ActionApproval:
    if approval.user_id != user_id:
        raise NotFound("approval not found")
    _check_pending(approval)
    approval.status = "rejected"
    approval.rejected_at = datetime.now(UTC)
    await record_audit(
        session,
        user_id=user_id,
        actor="user",
        event_type="approval.reject",
        target_type="approval",
        target_id=approval.id,
        details={"via": via, "reason": reason or ""},
    )
    fu = await session.scalar(select(m.FollowUp).where(m.FollowUp.approval_id == approval.id))
    if fu is not None:
        fu.status = "cancelled"
    await session.flush()
    return approval


async def edit(
    session: AsyncSession,
    user_id: uuid.UUID,
    approval: m.ActionApproval,
    *,
    subject: str | None,
    body: str,
    destination: dict[str, Any] | None,
    via: str,
) -> m.ActionApproval:
    """Editing invalidates the old approval and creates a new pending one with the same payload."""
    await reject(session, user_id, approval, via=via, reason="edited")
    new = await create_approval(
        session,
        user_id,
        action_type=approval.action_type,
        channel=approval.channel,
        destination=destination or approval.destination,
        subject=subject if subject is not None else approval.subject,
        body=body,
        attachments=approval.attachments,
        payload=approval.payload,
        preview_channel=approval.preview_channel,
        related_application_id=approval.related_application_id,
        actor="user",
    )
    fu = await session.scalar(select(m.FollowUp).where(m.FollowUp.approval_id == approval.id))
    if fu is not None:
        fu.approval_id = new.id
        fu.status = "drafted"
    return new


async def execute(approval_id: uuid.UUID) -> dict[str, Any]:
    """Worker entry point. Runs exactly once per approval: approved -> executing -> executed|failed."""
    import app.approvals.executors  # noqa: F401  (registers executors)

    async with get_session_factory()() as session:
        approval = await session.get(m.ActionApproval, approval_id)
        if approval is None:
            return {"status": "missing"}
        if approval.status != "approved":
            return {"status": approval.status, "skipped": True}
        approval.status = "executing"
        await session.commit()
        executor = _executors.get(approval.action_type)
        try:
            if executor is None:
                raise AppError(f"no executor for {approval.action_type}")
            result = await executor(session, approval)
            approval.status = "executed"
            approval.executed_at = datetime.now(UTC)
            approval.result = result
            await record_audit(
                session,
                user_id=approval.user_id,
                actor="system",
                event_type="approval.executed",
                target_type="approval",
                target_id=approval.id,
                details={"action_type": approval.action_type, "result": {k: v for k, v in result.items() if k != "text"}},
            )
            await _after_success(session, approval)
            await session.commit()
            return {"status": "executed", **result}
        except Exception as exc:  # noqa: BLE001
            await session.rollback()
            approval = await session.get(m.ActionApproval, approval_id)
            if approval is not None:
                approval.status = "failed"
                approval.error = f"{type(exc).__name__}: {exc}"[:2000]
                await record_audit(
                    session,
                    user_id=approval.user_id,
                    actor="system",
                    event_type="approval.failed",
                    target_type="approval",
                    target_id=approval.id,
                    details={"error": approval.error},
                )
                await session.commit()
            log.warning("approval execution failed", approval_id=str(approval_id), error=str(exc))
            return {"status": "failed", "error": str(exc)}


async def _after_success(session: AsyncSession, approval: m.ActionApproval) -> None:
    now = datetime.now(UTC)
    fu = await session.scalar(select(m.FollowUp).where(m.FollowUp.approval_id == approval.id))
    if fu is not None:
        fu.status = "sent"
    if approval.related_application_id:
        app = await session.get(m.Application, approval.related_application_id)
        if app is not None:
            app.last_contact_at = now
            if fu is not None:
                app.next_follow_up_at = now + timedelta(days=7)


async def expire_stale() -> int:
    async with get_session_factory()() as session:
        rows = (
            await session.scalars(
                select(m.ActionApproval).where(
                    m.ActionApproval.status == "pending", m.ActionApproval.expires_at < datetime.now(UTC)
                )
            )
        ).all()
        for row in rows:
            row.status = "expired"
        await session.commit()
        return len(rows)


async def list_for_user(session: AsyncSession, user_id: uuid.UUID, *, status: str | None, limit: int) -> list[m.ActionApproval]:
    stmt = select(m.ActionApproval).where(m.ActionApproval.user_id == user_id)
    if status:
        stmt = stmt.where(m.ActionApproval.status == status)
    return list((await session.scalars(stmt.order_by(m.ActionApproval.created_at.desc()).limit(limit))).all())
