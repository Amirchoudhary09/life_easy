"""All background tasks. Each takes the arq context (None when run inline) plus keyword args."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import delete, select

from app.core.logging import get_logger
from app.db import models as m
from app.db.session import get_session_factory
from app.tasks.runner import task

log = get_logger(__name__)


@task("purge_user")
async def purge_user(ctx: Any, *, user_id: str) -> dict[str, Any]:
    """Hard-delete a soft-deleted account: files, then rows (cascades), then the user."""
    from app.resumes.storage import get_storage

    uid = uuid.UUID(user_id)
    async with get_session_factory()() as session:
        user = await session.get(m.User, uid)
        if user is None or user.deleted_at is None:
            return {"status": "skipped"}
        storage = get_storage()
        resumes = (await session.scalars(select(m.Resume).where(m.Resume.user_id == uid))).all()
        for resume in resumes:
            try:
                await storage.delete(resume.object_key)
            except Exception:  # noqa: BLE001
                log.warning("could not delete resume object", key=resume.object_key)
        # audit rows keep a null user_id (SET NULL) so the deletion itself stays on record
        await session.execute(delete(m.User).where(m.User.id == uid))
        await session.commit()
    log.info("user purged", user_id=user_id)
    return {"status": "purged"}


@task("process_inbound_message")
async def process_inbound_message(
    ctx: Any,
    *,
    channel: str,
    external_id: str,
    text: str,
    event_id: str,
    display_name: str | None = None,
    button_id: str | None = None,
    reply_to: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from app.channels.pipeline import handle_inbound

    return await handle_inbound(
        channel=channel,
        external_id=external_id,
        text=text,
        event_id=event_id,
        display_name=display_name,
        button_id=button_id,
        reply_to=reply_to or {},
    )


@task("execute_approval")
async def execute_approval(ctx: Any, *, approval_id: str) -> dict[str, Any]:
    from app.approvals.service import execute

    return await execute(uuid.UUID(approval_id))


@task("ingest_jobs")
async def ingest_jobs(ctx: Any, *, sources: list[str] | None = None) -> dict[str, Any]:
    from app.jobs.ingest import run_ingest

    return await run_ingest(only=sources)


@task("match_user")
async def match_user(ctx: Any, *, user_id: str, limit: int = 50) -> dict[str, Any]:
    from app.jobs.matching import refresh_matches_for_user

    return await refresh_matches_for_user(uuid.UUID(user_id), limit=limit)


@task("parse_resume")
async def parse_resume(ctx: Any, *, resume_id: str) -> dict[str, Any]:
    from app.resumes.service import parse_and_store

    return await parse_and_store(uuid.UUID(resume_id))


@task("daily_digest")
async def daily_digest(ctx: Any, *, user_id: str | None = None) -> dict[str, Any]:
    from app.automations.digest import run_daily_digest

    return await run_daily_digest(uuid.UUID(user_id) if user_id else None)


@task("follow_ups")
async def follow_ups(ctx: Any) -> dict[str, Any]:
    from app.automations.followups import run_follow_ups

    return await run_follow_ups()


@task("inbox_watch")
async def inbox_watch(ctx: Any, *, user_id: str | None = None) -> dict[str, Any]:
    from app.automations.inbox_watch import run_inbox_watch

    return await run_inbox_watch(uuid.UUID(user_id) if user_id else None)


@task("interview_prep")
async def interview_prep(ctx: Any) -> dict[str, Any]:
    from app.automations.interview_prep import run_interview_prep

    return await run_interview_prep()


@task("weekly_report")
async def weekly_report(ctx: Any, *, user_id: str | None = None) -> dict[str, Any]:
    from app.automations.weekly_report import run_weekly_report

    return await run_weekly_report(uuid.UUID(user_id) if user_id else None)


@task("expire_approvals")
async def expire_approvals(ctx: Any) -> dict[str, Any]:
    from app.approvals.service import expire_stale

    return {"expired": await expire_stale()}


@task("purge_expired_contacts")
async def purge_expired_contacts(ctx: Any) -> dict[str, Any]:
    from datetime import UTC, datetime

    async with get_session_factory()() as session:
        result = await session.execute(delete(m.RecruiterContact).where(m.RecruiterContact.expires_at < datetime.now(UTC)))
        await session.commit()
    return {"deleted": result.rowcount}
