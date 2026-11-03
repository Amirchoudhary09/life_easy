"""Inbox watching: spot interview invites, rejections and offers, update the tracker, tell the user."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from app.ai.llm import get_llm, untrusted
from app.ai.usage import charge, ensure_within_limit
from app.applications.service import set_status
from app.automations.notify import notify_user
from app.core.errors import AppError
from app.core.logging import get_logger
from app.db import models as m
from app.db.session import get_session_factory
from app.email.service import EMAIL_PROVIDERS, provider_for

log = get_logger(__name__)
MAX_PER_RUN = 20

CLASSIFY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "category": {
            "type": "string",
            "enum": ["interview_invite", "rejection", "offer", "recruiter_reply", "assessment", "other"],
        },
        "company": {"type": "string"},
        "confidence": {"type": "number"},
        "summary": {"type": "string"},
    },
    "required": ["category", "confidence"],
}

STATUS_FOR = {
    "interview_invite": "interview",
    "rejection": "rejected",
    "offer": "offer",
    "assessment": "screening",
    "recruiter_reply": "screening",
}


async def run_inbox_watch(user_id: uuid.UUID | None = None) -> dict[str, Any]:
    processed = updated = 0
    async with get_session_factory()() as session:
        stmt = select(m.OAuthConnection).where(
            m.OAuthConnection.revoked_at.is_(None), m.OAuthConnection.provider.in_(EMAIL_PROVIDERS)
        )
        if user_id is not None:
            stmt = stmt.where(m.OAuthConnection.user_id == user_id)
        conns = (await session.scalars(stmt)).all()
        for conn in conns:
            try:
                p, u = await _watch_connection(session, conn)
                processed += p
                updated += u
            except AppError as exc:
                conn.last_error = exc.message[:500]
                log.warning("inbox watch failed", connection=str(conn.id), error=exc.message)
            await session.commit()
    return {"processed": processed, "updated": updated}


async def _watch_connection(session, conn: m.OAuthConnection) -> tuple[int, int]:  # type: ignore[no-untyped-def]
    now = datetime.now(UTC)
    last = (conn.extra or {}).get("last_inbox_check")
    since = datetime.fromisoformat(last) if last else now - timedelta(hours=24)
    provider = await provider_for(session, conn)
    items = await provider.list_recent(since=since, max_results=MAX_PER_RUN)
    apps = (
        await session.scalars(
            select(m.Application).where(
                m.Application.user_id == conn.user_id, m.Application.status.in_(("applied", "screening", "interview", "offer"))
            )
        )
    ).all()
    if not apps:
        conn.extra = {**(conn.extra or {}), "last_inbox_check": now.isoformat()}
        return len(items), 0
    updated = 0
    llm = get_llm()
    for item in items:
        if item.received_at and item.received_at < since:
            continue
        candidates = [
            a for a in apps if a.company.lower().split()[0] in (item.from_addr + " " + item.subject + " " + item.snippet).lower()
        ]
        if not candidates:
            continue
        try:
            await ensure_within_limit(session, conn.user_id)
        except AppError:
            break
        prompt = (
            "Classify this email for a job seeker's application tracker.\n"
            + untrusted(f"From: {item.from_addr}\nSubject: {item.subject}\n{item.snippet}", "email")
            + "\nKnown applications: "
            + "; ".join(f"{a.company} - {a.title}" for a in candidates)
        )
        data = await llm.json(
            system="You classify job-search emails. Be conservative: use 'other' unless the email clearly is one of the categories.",
            prompt=prompt,
            schema=CLASSIFY_SCHEMA,
            max_tokens=300,
        )
        await charge(session, conn.user_id, "llm")
        category = str(data.get("category", "other"))
        if category == "other" or float(data.get("confidence", 0)) < 0.7:
            continue
        company = str(data.get("company") or "").lower()
        app = next((a for a in candidates if company and company in a.company.lower()), candidates[0])
        new_status = STATUS_FOR.get(category)
        if new_status and app.status != new_status and not (app.status == "interview" and new_status == "screening"):
            await set_status(session, conn.user_id, app, new_status, note=f"Inbox: {item.subject[:120]}", source="inbox")
            updated += 1
        app.last_contact_at = item.received_at or now
        label = category.replace("_", " ")
        await notify_user(
            session,
            conn.user_id,
            f'Inbox update - {label}: {app.title} at {app.company}\n"{item.subject}"\n{data.get("summary", "")}'.strip(),
            kind="inbox",
        )
    conn.extra = {**(conn.extra or {}), "last_inbox_check": now.isoformat()}
    return len(items), updated
