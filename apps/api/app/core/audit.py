"""Insert-only audit trail for consequential actions."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.request_id import current_request_id
from app.db.models import AuditEvent


async def record_audit(
    session: AsyncSession,
    *,
    user_id: uuid.UUID | None,
    actor: str,
    event_type: str,
    target_type: str | None = None,
    target_id: str | uuid.UUID | None = None,
    details: dict[str, Any] | None = None,
) -> AuditEvent:
    event = AuditEvent(
        user_id=user_id,
        actor=actor,
        event_type=event_type,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        details=details or {},
        request_id=current_request_id() or None,
    )
    session.add(event)
    await session.flush()
    return event
