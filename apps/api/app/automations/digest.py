"""Daily job digest: refresh matches and send the best new ones with Save / Skip / Tailor buttons."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.automations.notify import notify_user
from app.channels.base import Button
from app.core.logging import get_logger
from app.db import models as m
from app.db.session import get_session_factory
from app.jobs.matching import refresh_matches_for_user

log = get_logger(__name__)
DIGEST_SIZE = 5
MIN_SCORE = 40.0


def _local_hour(tz_name: str) -> int:
    try:
        return datetime.now(ZoneInfo(tz_name)).hour
    except Exception:  # noqa: BLE001
        return datetime.now(UTC).hour


async def run_daily_digest(user_id: uuid.UUID | None = None) -> dict[str, Any]:
    sent = 0
    async with get_session_factory()() as session:
        stmt = select(m.Profile).where(m.Profile.digest_enabled.is_(True))
        if user_id is not None:
            stmt = stmt.where(m.Profile.user_id == user_id)
        profiles = (await session.scalars(stmt)).all()
        targets = []
        for p in profiles:
            hour = int((p.preferences or {}).get("digest_hour_local", 9))
            if user_id is not None or _local_hour(p.timezone) == hour:
                targets.append(p.user_id)
    for uid in targets:
        try:
            await refresh_matches_for_user(uid, limit=30)
            if await _send_digest(uid):
                sent += 1
        except Exception:  # noqa: BLE001
            log.exception("digest failed", user_id=str(uid))
    return {"users": len(targets), "sent": sent}


async def _send_digest(user_id: uuid.UUID) -> bool:
    async with get_session_factory()() as session:
        stmt = (
            select(m.JobMatch, m.Job)
            .join(m.Job, m.Job.id == m.JobMatch.job_id)
            .where(
                m.JobMatch.user_id == user_id,
                m.JobMatch.status == "suggested",
                m.JobMatch.digest_sent_at.is_(None),
                m.JobMatch.score >= MIN_SCORE,
            )
            .order_by(m.JobMatch.score.desc())
            .limit(DIGEST_SIZE)
        )
        rows = (await session.execute(stmt)).all()
        if not rows:
            return False
        now = datetime.now(UTC)
        lines = [f"Your top {len(rows)} new job matches today:"]
        for i, (jm, job) in enumerate(rows, 1):
            lines.append(f"{i}. {job.title} at {job.company} ({job.location or 'location n/a'}) - {int(float(jm.score))}% match")
        await notify_user(session, user_id, "\n".join(lines), kind="digest")
        for jm, job in rows:
            why = jm.explanation.get("summary") or ""
            text = f"{job.title} at {job.company}\n{job.location or ''}{' - remote' if job.remote else ''}\n{why}\n{job.apply_url}".strip()
            await notify_user(
                session,
                user_id,
                text,
                buttons=[
                    Button(id=f"save:{job.id.hex}", label="Save"),
                    Button(id=f"skip:{job.id.hex}", label="Skip"),
                    Button(id=f"tailor:{job.id.hex}", label="Tailor resume"),
                ],
                kind="digest_item",
            )
            jm.digest_sent_at = now
        await session.commit()
        return True
