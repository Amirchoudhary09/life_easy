from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.schemas import TokenPair
from app.config import get_settings
from app.core.audit import record_audit
from app.core.errors import Conflict, Unauthorized
from app.db.models import Profile, RefreshToken, User
from app.security.jwt import create_access_token, hash_refresh_token, new_refresh_token
from app.security.passwords import hash_password, verify_password


async def issue_tokens(session: AsyncSession, user: User) -> TokenPair:
    raw, token_hash, expires = new_refresh_token()
    session.add(RefreshToken(user_id=user.id, token_hash=token_hash, expires_at=expires))
    await session.flush()
    settings = get_settings()
    return TokenPair(
        access_token=create_access_token(user.id),
        refresh_token=raw,
        expires_in=settings.access_token_minutes * 60,
    )


async def register(session: AsyncSession, *, email: str, password: str, display_name: str | None) -> User:
    email = email.strip().lower()
    existing = await session.scalar(select(User).where(User.email == email))
    if existing is not None:
        raise Conflict("an account with this email already exists")
    user = User(email=email, display_name=display_name, password_hash=hash_password(password))
    session.add(user)
    await session.flush()
    session.add(Profile(user_id=user.id))
    await record_audit(session, user_id=user.id, actor="user", event_type="auth.register")
    return user


async def authenticate(session: AsyncSession, *, email: str, password: str) -> User:
    email = email.strip().lower()
    user = await session.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(password, user.password_hash):
        raise Unauthorized("invalid email or password")
    if not user.is_active or user.deleted_at is not None:
        raise Unauthorized("account is not active")
    await record_audit(session, user_id=user.id, actor="user", event_type="auth.login")
    return user


async def rotate_refresh_token(session: AsyncSession, raw_token: str) -> User:
    """Validate a refresh token, revoke it, and return the user so new tokens can be issued."""
    row = await session.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(raw_token)))
    now = datetime.now(UTC)
    if row is None or row.revoked_at is not None or row.expires_at < now:
        raise Unauthorized("refresh token is invalid or expired")
    row.revoked_at = now
    user = await session.get(User, row.user_id)
    if user is None or not user.is_active or user.deleted_at is not None:
        raise Unauthorized("account is not active")
    return user


async def revoke_refresh_token(session: AsyncSession, raw_token: str) -> None:
    row = await session.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(raw_token)))
    if row is not None and row.revoked_at is None:
        row.revoked_at = datetime.now(UTC)


async def revoke_all_sessions(session: AsyncSession, user_id: uuid.UUID) -> int:
    rows = (await session.scalars(select(RefreshToken).where(RefreshToken.user_id == user_id))).all()
    now = datetime.now(UTC)
    count = 0
    for row in rows:
        if row.revoked_at is None:
            row.revoked_at = now
            count += 1
    return count
