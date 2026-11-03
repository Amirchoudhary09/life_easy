from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.core.errors import AppError, NotFound
from app.db import models as m

FOLLOW_UP_AFTER_DAYS = 7
ACTIVE_STATUSES = ("applied", "screening", "interview")


async def _add_event(session: AsyncSession, app: m.Application, user_id: uuid.UUID, **fields: Any) -> None:
    """Timeline events get strictly increasing timestamps per application (coarse clocks would tie)."""
    await session.flush()
    last = await session.scalar(
        select(func.max(m.ApplicationEvent.created_at)).where(m.ApplicationEvent.application_id == app.id)
    )
    now = datetime.now(UTC)
    if last is not None:
        last = last if last.tzinfo else last.replace(tzinfo=UTC)
        if now <= last:
            now = last + timedelta(microseconds=1)
    session.add(m.ApplicationEvent(application_id=app.id, user_id=user_id, created_at=now, **fields))


async def get_owned(session: AsyncSession, user_id: uuid.UUID, application_id: uuid.UUID) -> m.Application:
    app = await session.get(m.Application, application_id)
    if app is None or app.user_id != user_id:
        raise NotFound("application not found")
    return app


async def create_application(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    job: m.Job | None = None,
    company: str | None = None,
    title: str | None = None,
    status: str = "planned",
    source_url: str | None = None,
    notes: str | None = None,
    source: str = "user",
) -> m.Application:
    if job is not None:
        existing = await session.scalar(
            select(m.Application).where(m.Application.user_id == user_id, m.Application.job_id == job.id)
        )
        if existing is not None:
            if status != existing.status and status != "planned":
                await set_status(session, user_id, existing, status, source=source)
            return existing
        company, title, source_url = job.company, job.title, job.apply_url
    if not company or not title:
        raise AppError("company and title are required when no job is linked")
    app = m.Application(
        user_id=user_id,
        job_id=job.id if job else None,
        company=company[:200],
        title=title[:300],
        status="planned",
        source_url=source_url,
        notes=notes,
    )
    session.add(app)
    await session.flush()
    await _add_event(session, app, user_id, from_status=None, to_status="planned", source=source)
    if status != "planned":
        await set_status(session, user_id, app, status, source=source)
    await record_audit(
        session,
        user_id=user_id,
        actor="user" if source == "user" else "agent",
        event_type="application.create",
        target_type="application",
        target_id=app.id,
    )
    return app


async def set_status(
    session: AsyncSession,
    user_id: uuid.UUID,
    app: m.Application,
    new_status: str,
    *,
    note: str | None = None,
    source: str = "user",
) -> m.Application:
    if new_status not in m.APPLICATION_STATUSES:
        raise AppError(f"unknown status {new_status!r}")
    old = app.status
    now = datetime.now(UTC)
    app.status = new_status
    if new_status == "applied" and app.applied_at is None:
        app.applied_at = now
    if new_status in ("applied", "screening") and app.next_follow_up_at is None:
        app.next_follow_up_at = now + timedelta(days=FOLLOW_UP_AFTER_DAYS)
    if new_status in ("offer", "accepted", "rejected", "withdrawn"):
        app.next_follow_up_at = None
    if old != new_status or note:
        await _add_event(session, app, user_id, from_status=old, to_status=new_status, note=note, source=source)
    await session.flush()
    return app


async def list_applications(
    session: AsyncSession, user_id: uuid.UUID, *, status: str | None, limit: int, offset: int
) -> tuple[list[m.Application], int]:
    stmt = select(m.Application).where(m.Application.user_id == user_id)
    if status:
        stmt = stmt.where(m.Application.status == status)
    total = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = (await session.scalars(stmt.order_by(m.Application.updated_at.desc()).limit(limit).offset(offset))).all()
    return list(rows), int(total)


async def add_interview(
    session: AsyncSession,
    user_id: uuid.UUID,
    app: m.Application,
    *,
    scheduled_at: datetime,
    kind: str,
    location: str | None,
    notes: str | None,
) -> m.Interview:
    interview = m.Interview(
        user_id=user_id, application_id=app.id, scheduled_at=scheduled_at, kind=kind, location=location, notes=notes
    )
    session.add(interview)
    if app.status in ("planned", "applied", "screening"):
        await set_status(session, user_id, app, "interview", note=f"{kind} scheduled {scheduled_at.isoformat()}")
    await session.flush()
    return interview


async def schedule_follow_up(session: AsyncSession, user_id: uuid.UUID, app: m.Application, *, due_at: datetime) -> m.FollowUp:
    fu = m.FollowUp(user_id=user_id, application_id=app.id, due_at=due_at, status="pending")
    session.add(fu)
    app.next_follow_up_at = due_at
    await session.flush()
    return fu


async def stats(session: AsyncSession, user_id: uuid.UUID) -> dict[str, Any]:
    now = datetime.now(UTC)
    rows = (
        await session.execute(
            select(m.Application.status, func.count()).where(m.Application.user_id == user_id).group_by(m.Application.status)
        )
    ).all()
    by_status = {status: int(count) for status, count in rows}
    applied_7 = (
        await session.scalar(
            select(func.count())
            .select_from(m.Application)
            .where(m.Application.user_id == user_id, m.Application.applied_at >= now - timedelta(days=7))
        )
        or 0
    )
    upcoming = (
        await session.scalar(
            select(func.count()).select_from(m.Interview).where(m.Interview.user_id == user_id, m.Interview.scheduled_at >= now)
        )
        or 0
    )
    due = (
        await session.scalar(
            select(func.count())
            .select_from(m.Application)
            .where(
                m.Application.user_id == user_id,
                m.Application.next_follow_up_at <= now,
                m.Application.status.in_(ACTIVE_STATUSES),
            )
        )
        or 0
    )
    return {
        "by_status": by_status,
        "applied_last_7_days": int(applied_7),
        "interviews_upcoming": int(upcoming),
        "follow_ups_due": int(due),
    }
