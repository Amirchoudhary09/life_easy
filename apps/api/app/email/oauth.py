"""OAuth 2.0 (authorization code) for Google, Microsoft and LinkedIn. Tokens are stored encrypted."""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.errors import AppError, ProviderError, ProviderNotConfigured
from app.db import models as m
from app.security.crypto import get_secret_box

STATE_MINUTES = 10


def _provider_config(provider: str) -> dict[str, Any]:
    s = get_settings()
    if provider == "google":
        return {
            "client_id": s.google_client_id,
            "client_secret": s.google_client_secret,
            "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
            "token_url": "https://oauth2.googleapis.com/token",
            "userinfo_url": "https://openidconnect.googleapis.com/v1/userinfo",
            "scopes": [
                "openid",
                "email",
                "https://www.googleapis.com/auth/gmail.send",
                "https://www.googleapis.com/auth/gmail.readonly",
            ],
            "extra_auth": {"access_type": "offline", "prompt": "consent"},
        }
    if provider == "microsoft":
        base = f"https://login.microsoftonline.com/{s.microsoft_tenant}/oauth2/v2.0"
        return {
            "client_id": s.microsoft_client_id,
            "client_secret": s.microsoft_client_secret,
            "auth_url": f"{base}/authorize",
            "token_url": f"{base}/token",
            "userinfo_url": "https://graph.microsoft.com/v1.0/me",
            "scopes": ["openid", "email", "offline_access", "User.Read", "Mail.Send", "Mail.Read"],
            "extra_auth": {"response_mode": "query"},
        }
    if provider == "linkedin":
        return {
            "client_id": s.linkedin_client_id,
            "client_secret": s.linkedin_client_secret,
            "auth_url": "https://www.linkedin.com/oauth/v2/authorization",
            "token_url": "https://www.linkedin.com/oauth/v2/accessToken",
            "userinfo_url": "https://api.linkedin.com/v2/userinfo",
            "scopes": ["openid", "profile", "email", "w_member_social"],
            "extra_auth": {},
        }
    raise AppError(f"unknown provider {provider}")


def redirect_uri(provider: str) -> str:
    return f"{get_settings().public_api_url}/api/v1/connections/oauth/{provider}/callback"


def make_state(user_id: uuid.UUID, provider: str) -> str:
    payload = {
        "sub": str(user_id),
        "provider": provider,
        "nonce": secrets.token_hex(8),
        "type": "oauth_state",
        "exp": datetime.now(UTC) + timedelta(minutes=STATE_MINUTES),
    }
    return jwt.encode(payload, get_settings().jwt_secret, algorithm="HS256")


def read_state(state: str) -> tuple[uuid.UUID, str]:
    try:
        payload = jwt.decode(state, get_settings().jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise AppError("invalid or expired OAuth state") from exc
    if payload.get("type") != "oauth_state":
        raise AppError("invalid OAuth state")
    return uuid.UUID(payload["sub"]), str(payload["provider"])


def authorize_url(user_id: uuid.UUID, provider: str) -> str:
    cfg = _provider_config(provider)
    if not cfg["client_id"] or not cfg["client_secret"]:
        raise ProviderNotConfigured(f"{provider} OAuth is not configured")
    params = {
        "client_id": cfg["client_id"],
        "redirect_uri": redirect_uri(provider),
        "response_type": "code",
        "scope": " ".join(cfg["scopes"]),
        "state": make_state(user_id, provider),
        **cfg["extra_auth"],
    }
    return f"{cfg['auth_url']}?{urlencode(params)}"


async def exchange_code(provider: str, code: str) -> dict[str, Any]:
    cfg = _provider_config(provider)
    data = {
        "client_id": cfg["client_id"],
        "client_secret": cfg["client_secret"],
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri(provider),
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(cfg["token_url"], data=data, headers={"Accept": "application/json"})
        if resp.is_error:
            raise ProviderError(f"{provider} token exchange failed with HTTP {resp.status_code}")
        tokens = resp.json()
        info = await client.get(cfg["userinfo_url"], headers={"Authorization": f"Bearer {tokens.get('access_token', '')}"})
        profile = info.json() if not info.is_error else {}
    email = profile.get("email") or profile.get("mail") or profile.get("userPrincipalName") or ""
    return {"tokens": tokens, "email": email, "profile": profile}


async def refresh_access_token(provider: str, refresh_token: str) -> dict[str, Any]:
    cfg = _provider_config(provider)
    data = {
        "client_id": cfg["client_id"],
        "client_secret": cfg["client_secret"],
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(cfg["token_url"], data=data, headers={"Accept": "application/json"})
    if resp.is_error:
        raise ProviderError(f"{provider} token refresh failed with HTTP {resp.status_code}")
    return resp.json()


async def store_connection(
    session: AsyncSession, user_id: uuid.UUID, provider: str, exchanged: dict[str, Any]
) -> m.OAuthConnection:
    tokens = exchanged["tokens"]
    email = (exchanged.get("email") or "").lower()
    if not email and provider != "linkedin":
        raise ProviderError(f"{provider} did not return the account email")
    box = get_secret_box()
    account = email or provider
    conn = await session.scalar(
        select(m.OAuthConnection).where(
            m.OAuthConnection.user_id == user_id,
            m.OAuthConnection.provider == provider,
            m.OAuthConnection.account_email == account,
        )
    )
    if conn is None:
        conn = m.OAuthConnection(user_id=user_id, provider=provider, account_email=account)
        session.add(conn)
    conn.scopes = str(tokens.get("scope", "")).split()
    conn.access_token_enc = box.encrypt(tokens["access_token"])
    if tokens.get("refresh_token"):
        conn.refresh_token_enc = box.encrypt(tokens["refresh_token"])
    conn.token_expires_at = datetime.now(UTC) + timedelta(seconds=int(tokens.get("expires_in", 3600)))
    conn.revoked_at = None
    conn.last_error = None
    profile = exchanged.get("profile") or {}
    if provider == "linkedin" and profile.get("sub"):
        conn.extra = {**conn.extra, "person_urn": f"urn:li:person:{profile['sub']}", "name": profile.get("name", "")}
    await session.flush()
    return conn


async def ensure_access_token(session: AsyncSession, conn: m.OAuthConnection) -> str:
    """Return a valid access token, refreshing (and re-encrypting) when it is about to expire."""
    box = get_secret_box()
    if conn.revoked_at is not None:
        raise ProviderError("connection was disconnected")
    expiring = conn.token_expires_at is None or conn.token_expires_at <= datetime.now(UTC) + timedelta(minutes=2)
    if expiring and conn.refresh_token_enc:
        tokens = await refresh_access_token(conn.provider, box.decrypt(conn.refresh_token_enc))
        conn.access_token_enc = box.encrypt(tokens["access_token"])
        if tokens.get("refresh_token"):
            conn.refresh_token_enc = box.encrypt(tokens["refresh_token"])
        conn.token_expires_at = datetime.now(UTC) + timedelta(seconds=int(tokens.get("expires_in", 3600)))
        await session.flush()
    if not conn.access_token_enc:
        raise ProviderError("connection has no access token")
    return box.decrypt(conn.access_token_enc)
