"""Per-user daily usage counters: plan limits and cost tracking."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.errors import LimitExceeded
from app.db import models as m


def today() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


async def _counter(session: AsyncSession, user_id: uuid.UUID, kind: str) -> m.UsageCounter:
    day = today()
    row = await session.scalar(
        select(m.UsageCounter).where(m.UsageCounter.user_id == user_id, m.UsageCounter.day == day, m.UsageCounter.kind == kind)
    )
    if row is None:
        row = m.UsageCounter(user_id=user_id, day=day, kind=kind, count=0)
        session.add(row)
        await session.flush()
    return row


async def charge(session: AsyncSession, user_id: uuid.UUID, kind: str, *, tokens_in: int = 0, tokens_out: int = 0) -> None:
    row = await _counter(session, user_id, kind)
    row.count += 1
    row.tokens_in += tokens_in
    row.tokens_out += tokens_out


async def ensure_within_limit(session: AsyncSession, user_id: uuid.UUID, kind: str = "llm") -> None:
    limit = get_settings().max_llm_calls_per_user_per_day
    row = await _counter(session, user_id, kind)
    if row.count >= limit:
        raise LimitExceeded(f"daily {kind} limit of {limit} reached; try again tomorrow")


async def usage_summary(session: AsyncSession, user_id: uuid.UUID) -> list[dict[str, object]]:
    rows = (await session.scalars(select(m.UsageCounter).where(m.UsageCounter.user_id == user_id))).all()
    return [
        {"day": r.day, "kind": r.kind, "count": r.count, "tokens_in": r.tokens_in, "tokens_out": r.tokens_out}
        for r in sorted(rows, key=lambda r: (r.day, r.kind), reverse=True)[:60]
    ]
