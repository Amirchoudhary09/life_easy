"""Bind a messaging identity to a Life Easy account with a one-time code from the dashboard."""

from __future__ import annotations

import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.core.errors import AppError
from app.db import models as m

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I
CODE_MINUTES = 15
_LINK = re.compile(r"^\s*(?:/)?link\s+([A-Za-z0-9]{6})\s*$", re.I)


async def create_link_code(session: AsyncSession, user_id: uuid.UUID) -> m.LinkCode:
    code = "".join(secrets.choice(ALPHABET) for _ in range(6))
    row = m.LinkCode(user_id=user_id, code=code, expires_at=datetime.now(UTC) + timedelta(minutes=CODE_MINUTES))
    session.add(row)
    await session.flush()
    return row


def parse_link_command(text: str) -> str | None:
    match = _LINK.match(text or "")
    return match.group(1).upper() if match else None


async def find_identity(session: AsyncSession, provider: str, external_id: str) -> m.ChannelIdentity | None:
    return await session.scalar(
        select(m.ChannelIdentity).where(
            m.ChannelIdentity.provider == provider,
            m.ChannelIdentity.external_id == external_id,
            m.ChannelIdentity.revoked_at.is_(None),
        )
    )


async def link_identity(
    session: AsyncSession, *, provider: str, external_id: str, code: str, display_name: str | None
) -> m.ChannelIdentity:
    row = await session.scalar(select(m.LinkCode).where(m.LinkCode.code == code.upper()))
    now = datetime.now(UTC)
    if row is None or row.used_at is not None or row.expires_at < now:
        raise AppError("that link code is invalid or expired; generate a new one in the dashboard")
    user = await session.get(m.User, row.user_id)
    if user is None or not user.is_active or user.deleted_at is not None:
        raise AppError("account is not active")
    row.used_at = now
    existing = await session.scalar(
        select(m.ChannelIdentity).where(m.ChannelIdentity.provider == provider, m.ChannelIdentity.external_id == external_id)
    )
    if existing is not None:
        existing.user_id = user.id
        existing.display_name = display_name
        existing.verified_at = now
        existing.revoked_at = None
        identity = existing
    else:
        identity = m.ChannelIdentity(user_id=user.id, provider=provider, external_id=external_id, display_name=display_name)
        session.add(identity)
    await session.flush()
    await record_audit(
        session,
        user_id=user.id,
        actor="user",
        event_type="channel.link",
        target_type="channel_identity",
        target_id=identity.id,
        details={"provider": provider},
    )
    return identity


async def revoke_identity(session: AsyncSession, user_id: uuid.UUID, identity_id: uuid.UUID) -> None:
    identity = await session.get(m.ChannelIdentity, identity_id)
    if identity is None or identity.user_id != user_id:
        raise AppError("channel not found")
    identity.revoked_at = datetime.now(UTC)
    await record_audit(
        session,
        user_id=user_id,
        actor="user",
        event_type="channel.unlink",
        target_type="channel_identity",
        target_id=identity.id,
        details={"provider": identity.provider},
    )
