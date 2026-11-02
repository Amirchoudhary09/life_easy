import hashlib
import json
from typing import Annotated
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, StringConstraints

from app.auth import current_user
from app.db import get_db

router = APIRouter(prefix="/api/v1/approvals", tags=["Approvals"])
ACTIONS = {"email.send", "linkedin.message", "linkedin.post", "whatsapp.message", "application.submit", "social.post"}


class ApprovalBody(BaseModel):
    action_type: str = Field(min_length=3, max_length=80)
    channel: str = Field(pattern="^(gmail|linkedin|whatsapp|other)$")
    recipient: str = Field(min_length=2, max_length=320)
    message: str = Field(min_length=1, max_length=20000)
    subject: str | None = Field(default=None, max_length=300)
    attachments: list[str] = Field(default_factory=list, max_length=10)
    metadata: dict = Field(default_factory=dict)


class ApprovalConfirmBody(BaseModel):
    confirm: bool
    content_hash: Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]


def digest(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()


@router.post("", status_code=201)
async def create_approval(body: ApprovalBody, user=Depends(current_user), db: asyncpg.Pool = Depends(get_db)):
    if body.action_type not in ACTIONS:
        raise HTTPException(status_code=400, detail="Unsupported external action")
    expected_channel = {
        "email.send": "gmail",
        "linkedin.message": "linkedin",
        "linkedin.post": "linkedin",
        "whatsapp.message": "whatsapp",
    }
    if body.action_type in expected_channel and body.channel != expected_channel[body.action_type]:
        raise HTTPException(status_code=400, detail="Channel does not match action type")
    payload = body.model_dump()
    content_hash = digest(payload)
    row = await db.fetchrow(
        """
        INSERT INTO action_approvals(user_id, action_type, payload, content_hash, status)
        VALUES($1, $2, $3::jsonb, $4, 'pending')
        RETURNING id, action_type, payload, content_hash, status, created_at
        """,
        user["id"], body.action_type, payload, content_hash,
    )
    return {"approval": dict(row), "requires_explicit_confirmation": True}


@router.get("")
async def list_approvals(user=Depends(current_user), db: asyncpg.Pool = Depends(get_db)):
    rows = await db.fetch(
        """
        SELECT id, action_type, payload, content_hash, status, created_at, approved_at, executed_at
        FROM action_approvals WHERE user_id = $1 ORDER BY created_at DESC LIMIT 100
        """,
        user["id"],
    )
    return {"approvals": [dict(row) for row in rows]}


@router.post("/{approval_id}/confirm")
async def confirm_approval(
    approval_id: UUID,
    body: ApprovalConfirmBody,
    user=Depends(current_user),
    db: asyncpg.Pool = Depends(get_db),
):
    async with db.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                SELECT id, action_type, payload, content_hash, status
                FROM action_approvals WHERE id = $1 AND user_id = $2 FOR UPDATE
                """,
                approval_id, user["id"],
            )
            if row is None:
                raise HTTPException(status_code=404, detail="Approval not found")
            if row["status"] != "pending":
                raise HTTPException(status_code=409, detail="Approval is no longer pending")
            actual_hash = digest(row["payload"])
            if body.content_hash != row["content_hash"] or actual_hash != row["content_hash"]:
                raise HTTPException(status_code=409, detail="Preview changed; review the latest message")
            status = "approved" if body.confirm else "cancelled"
            await conn.execute(
                """
                UPDATE action_approvals
                SET status = $1, approved_at = CASE WHEN $1 = 'approved' THEN now() ELSE NULL END
                WHERE id = $2 AND user_id = $3
                """,
                status, approval_id, user["id"],
            )
            await conn.execute(
                """
                INSERT INTO audit_events(user_id, event_type, resource_id, details)
                VALUES($1, $2, $3, $4::jsonb)
                """,
                user["id"], "approval." + status, approval_id,
                {"content_hash": row["content_hash"], "action_type": row["action_type"]},
            )
    # An approved record is still not sent until a separate execution worker exists.
    return {"approval_id": str(approval_id), "status": status, "execution": "not_sent_worker_pending"}
