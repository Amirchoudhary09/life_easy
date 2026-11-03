"""`current_user` dependency: Bearer access token -> active User row."""

from __future__ import annotations

import uuid

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Unauthorized
from app.db.models import User
from app.db.session import get_db
from app.security.jwt import TokenError, decode_access_token


def _bearer(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise Unauthorized("missing bearer token")
    return authorization.split(" ", 1)[1].strip()


async def current_user_id(authorization: str | None = Header(default=None)) -> uuid.UUID:
    try:
        return decode_access_token(_bearer(authorization))
    except TokenError as exc:
        raise Unauthorized(str(exc)) from exc


async def current_user(
    user_id: uuid.UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_db),
) -> User:
    user = await session.get(User, user_id)
    if user is None or not user.is_active or user.deleted_at is not None:
        raise Unauthorized("account is not active")
    return user
