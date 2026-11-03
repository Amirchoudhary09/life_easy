"""Send an interview prep pack the day before each interview."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from app.agent.tools import build_interview_prep
from app.automations.notify import notify_user
from app.core.errors import AppError
from app.core.logging import get_logger
from app.db import models as m
from app.db.session import get_session_factory

log = get_logger(__name__)
WINDOW_HOURS = 36


def format_prep(app: m.Application, interview: m.Interview, data: dict[str, Any]) -> str:
    lines = [
        f"Interview prep: {app.title} at {app.company}",
        f"When: {interview.scheduled_at.strftime('%a %d %b, %H:%M %Z')}"
        + (f"\nWhere: {interview.location}" if interview.location else ""),
    ]
    if data.get("company_overview"):
        lines += ["", str(data["company_overview"])]
    if data.get("likely_questions"):
        lines += ["", "Likely questions:"] + [f"- {q}" for q in data["likely_questions"][:8]]
    if data.get("questions_to_ask"):
        lines += ["", "Questions you can ask:"] + [f"- {q}" for q in data["questions_to_ask"][:5]]
    if data.get("tips"):
        lines += ["", "Tips:"] + [f"- {t}" for t in data["tips"][:5]]
    return "\n".join(lines)


async def run_interview_prep() -> dict[str, Any]:
    sent = 0
    async with get_session_factory()() as session:
        now = datetime.now(UTC)
        rows = (
            await session.execute(
                select(m.Interview, m.Application)
                .join(m.Application, m.Application.id == m.Interview.application_id)
                .where(
                    m.Interview.prep_sent_at.is_(None),
                    m.Interview.scheduled_at >= now,
                    m.Interview.scheduled_at <= now + timedelta(hours=WINDOW_HOURS),
                )
            )
        ).all()
        for interview, app in rows:
            try:
                data = await build_interview_prep(session, interview.user_id, app)
                await notify_user(session, interview.user_id, format_prep(app, interview, data), kind="interview_prep")
                interview.prep_sent_at = now
                sent += 1
            except AppError as exc:
                log.warning("interview prep skipped", interview_id=str(interview.id), error=exc.message)
        await session.commit()
    return {"sent": sent}
