"""Profile, data export and account deletion."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import current_user
from app.auth.service import revoke_all_sessions
from app.core.audit import record_audit
from app.db import models as m
from app.db.session import get_db
from app.me.schemas import ProfileOut, ProfileUpdate
from app.tasks.runner import enqueue

router = APIRouter(prefix="/api/v1/me", tags=["me"])


async def get_or_create_profile(session: AsyncSession, user_id) -> m.Profile:  # type: ignore[no-untyped-def]
    profile = await session.get(m.Profile, user_id)
    if profile is None:
        profile = m.Profile(user_id=user_id)
        session.add(profile)
        await session.flush()
    return profile


@router.get("/profile", response_model=ProfileOut)
async def read_profile(user: m.User = Depends(current_user), session: AsyncSession = Depends(get_db)) -> m.Profile:
    return await get_or_create_profile(session, user.id)


@router.patch("/profile", response_model=ProfileOut)
async def update_profile(
    body: ProfileUpdate, user: m.User = Depends(current_user), session: AsyncSession = Depends(get_db)
) -> m.Profile:
    profile = await get_or_create_profile(session, user.id)
    data = body.model_dump(exclude_unset=True)
    if "display_name" in data:
        user.display_name = data.pop("display_name")
    if "preferences" in data and data["preferences"] is not None:
        data["preferences"] = body.preferences.model_dump() if body.preferences else {}
    for key, value in data.items():
        setattr(profile, key, value)
    profile.embedding = None  # re-embedded lazily by the matcher
    await session.flush()
    return profile


def _row(obj: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for column in obj.__table__.columns:
        if column.name.endswith("_enc") or column.name == "password_hash" or column.name == "embedding":
            continue
        value = getattr(obj, column.name)
        out[column.name] = (
            value.isoformat()
            if isinstance(value, datetime)
            else (str(value) if value is not None and column.name.endswith("id") else value)
        )
    return out


@router.get("/export")
async def export_data(user: m.User = Depends(current_user), session: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Everything Life Easy stores about this user, as JSON (no secrets, no embeddings)."""
    export: dict[str, Any] = {"user": _row(user), "exported_at": datetime.now(UTC).isoformat()}
    tables: dict[str, Any] = {
        "profile": m.Profile,
        "resumes": m.Resume,
        "job_matches": m.JobMatch,
        "applications": m.Application,
        "application_events": m.ApplicationEvent,
        "interviews": m.Interview,
        "follow_ups": m.FollowUp,
        "recruiter_contacts": m.RecruiterContact,
        "conversations": m.Conversation,
        "messages": m.Message,
        "memory_items": m.MemoryItem,
        "oauth_connections": m.OAuthConnection,
        "action_approvals": m.ActionApproval,
        "audit_events": m.AuditEvent,
        "channel_identities": m.ChannelIdentity,
    }
    for name, model in tables.items():
        rows = (await session.scalars(select(model).where(model.user_id == user.id))).all()
        export[name] = [_row(r) for r in rows]
    await record_audit(session, user_id=user.id, actor="user", event_type="account.export")
    return export


@router.delete("", status_code=202)
async def delete_account(user: m.User = Depends(current_user), session: AsyncSession = Depends(get_db)) -> dict[str, str]:
    """Soft-delete now (no more logins, channels unlinked), hard purge by the worker."""
    now = datetime.now(UTC)
    user.is_active = False
    user.deleted_at = now
    await revoke_all_sessions(session, user.id)
    identities = (await session.scalars(select(m.ChannelIdentity).where(m.ChannelIdentity.user_id == user.id))).all()
    for identity in identities:
        identity.revoked_at = now
    await record_audit(session, user_id=user.id, actor="user", event_type="account.delete_requested")
    await session.commit()
    await enqueue("purge_user", user_id=str(user.id))
    return {"status": "deletion_scheduled"}
