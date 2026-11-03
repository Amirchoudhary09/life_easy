"""Weekly summary: what happened, what is due, one suggestion."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select

from app.automations.notify import notify_user
from app.core.logging import get_logger
from app.db import models as m
from app.db.session import get_session_factory

log = get_logger(__name__)


async def run_weekly_report(user_id: uuid.UUID | None = None) -> dict[str, Any]:
    sent = 0
    async with get_session_factory()() as session:
        stmt = select(m.Profile).where(m.Profile.digest_enabled.is_(True))
        if user_id is not None:
            stmt = stmt.where(m.Profile.user_id == user_id)
        profiles = (await session.scalars(stmt)).all()
        now = datetime.now(UTC)
        week_ago = now - timedelta(days=7)
        for p in profiles:
            uid = p.user_id
            applied = (
                await session.scalar(
                    select(func.count())
                    .select_from(m.Application)
                    .where(m.Application.user_id == uid, m.Application.applied_at >= week_ago)
                )
                or 0
            )
            replies = (
                await session.scalar(
                    select(func.count())
                    .select_from(m.ApplicationEvent)
                    .where(
                        m.ApplicationEvent.user_id == uid,
                        m.ApplicationEvent.source == "inbox",
                        m.ApplicationEvent.created_at >= week_ago,
                    )
                )
                or 0
            )
            interviews = (
                await session.scalar(
                    select(func.count())
                    .select_from(m.Interview)
                    .where(
                        m.Interview.user_id == uid,
                        m.Interview.scheduled_at >= now,
                        m.Interview.scheduled_at <= now + timedelta(days=7),
                    )
                )
                or 0
            )
            new_matches = (
                await session.scalar(
                    select(func.count())
                    .select_from(m.JobMatch)
                    .where(m.JobMatch.user_id == uid, m.JobMatch.created_at >= week_ago)
                )
                or 0
            )
            due = (
                await session.scalar(
                    select(func.count())
                    .select_from(m.Application)
                    .where(
                        m.Application.user_id == uid,
                        m.Application.next_follow_up_at <= now + timedelta(days=7),
                        m.Application.status.in_(("applied", "screening")),
                    )
                )
                or 0
            )
            if not any((applied, replies, interviews, new_matches, due)):
                continue
            suggestion = "Keep a steady pace: 3-5 well-targeted applications this week beat 20 generic ones."
            if applied == 0 and new_matches > 0:
                suggestion = f"You have {new_matches} new matches but no applications this week. Pick two and I'll tailor your resume for them."
            elif applied >= 5 and replies == 0:
                suggestion = "Many applications, no replies yet: let's review your resume keywords against the roles you want."
            text = (
                f"Your week in review\n"
                f"- Applications sent: {applied}\n- Replies detected: {replies}\n- Interviews in the next 7 days: {interviews}\n"
                f"- New matches: {new_matches}\n- Follow-ups due this week: {due}\n\n{suggestion}"
            )
            await notify_user(session, uid, text, kind="weekly_report")
            sent += 1
        await session.commit()
    return {"sent": sent}
