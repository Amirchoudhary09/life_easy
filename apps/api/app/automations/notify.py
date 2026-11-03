"""Deliver a proactive message to the user: their linked chat channel first, the dashboard inbox always."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.agent import _store, get_conversation
from app.channels.base import Button
from app.channels.pipeline import get_adapter
from app.core.errors import AppError
from app.core.logging import get_logger
from app.db import models as m

log = get_logger(__name__)
PREFERRED = ("whatsapp", "telegram")


async def notify_user(
    session: AsyncSession, user_id: uuid.UUID, text: str, *, buttons: list[Button] | None = None, kind: str = "notice"
) -> str:
    """Returns the channel used ('whatsapp', 'telegram' or 'dashboard')."""
    conv = await get_conversation(session, user_id, "notifications")
    await _store(session, conv, user_id, "assistant", text, {"kind": kind, "buttons": [b.__dict__ for b in (buttons or [])]})
    identities = (
        await session.scalars(
            select(m.ChannelIdentity).where(m.ChannelIdentity.user_id == user_id, m.ChannelIdentity.revoked_at.is_(None))
        )
    ).all()
    by_provider = {i.provider: i for i in identities}
    for provider in PREFERRED:
        identity = by_provider.get(provider)
        if identity is None:
            continue
        adapter = get_adapter(provider)
        if not adapter.configured():
            continue
        try:
            if buttons:
                await adapter.send_buttons(identity.external_id, text, buttons)
            else:
                await adapter.send_text(identity.external_id, text)
            return provider
        except AppError as exc:
            log.warning("notification send failed", provider=provider, error=exc.message)
    return "dashboard"
