"""Web dashboard chat: same agent as the messaging channels."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.agent import get_conversation, run
from app.approvals.schemas import ApprovalOut
from app.auth.deps import current_user
from app.db import models as m
from app.db.session import get_db
from app.security.ratelimit import rate_limit

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])


class ChatRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class ChatMessageOut(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    meta: dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatResponse(BaseModel):
    reply: str
    approvals: list[ApprovalOut]
    tool_calls: list[str]


@router.post("/messages", response_model=ChatResponse, dependencies=[Depends(rate_limit("chat", 60))])
async def send_message(
    body: ChatRequest, user: m.User = Depends(current_user), session: AsyncSession = Depends(get_db)
) -> ChatResponse:
    result = await run(session, user, body.text, channel="web")
    return ChatResponse(
        reply=result.reply, approvals=[ApprovalOut.model_validate(a) for a in result.approvals], tool_calls=result.tool_calls
    )


@router.get("/messages", response_model=list[ChatMessageOut])
async def history(
    limit: int = Query(default=50, ge=1, le=200), user: m.User = Depends(current_user), session: AsyncSession = Depends(get_db)
) -> list[m.Message]:
    conv = await get_conversation(session, user.id, "web")
    rows = (
        await session.scalars(
            select(m.Message).where(m.Message.conversation_id == conv.id).order_by(m.Message.created_at.desc()).limit(limit)
        )
    ).all()
    return list(reversed(rows))


@router.get("/notifications", response_model=list[ChatMessageOut])
async def notifications(
    limit: int = Query(default=30, ge=1, le=100), user: m.User = Depends(current_user), session: AsyncSession = Depends(get_db)
) -> list[m.Message]:
    conv = await get_conversation(session, user.id, "notifications")
    rows = (
        await session.scalars(
            select(m.Message).where(m.Message.conversation_id == conv.id).order_by(m.Message.created_at.desc()).limit(limit)
        )
    ).all()
    return list(rows)
