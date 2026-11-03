from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.approvals.schemas import ApprovalOut
from app.auth.deps import current_user
from app.db import models as m
from app.db.session import get_db
from app.linkedin import service
from app.linkedin.schemas import (
    MessageDraftOut,
    MessageDraftRequest,
    PostDraftOut,
    PostDraftRequest,
    PublishRequest,
    SendMessageRequest,
)
from app.security.ratelimit import rate_limit

router = APIRouter(prefix="/api/v1/linkedin", tags=["linkedin"])


@router.post("/drafts/post", response_model=PostDraftOut, dependencies=[Depends(rate_limit("draft", 30))])
async def draft_post(
    body: PostDraftRequest, user: m.User = Depends(current_user), session: AsyncSession = Depends(get_db)
) -> PostDraftOut:
    return PostDraftOut(**await service.draft_post(session, user.id, topic=body.topic, tone=body.tone, length=body.length))


@router.post("/drafts/message", response_model=MessageDraftOut, dependencies=[Depends(rate_limit("draft", 30))])
async def draft_message(
    body: MessageDraftRequest, user: m.User = Depends(current_user), session: AsyncSession = Depends(get_db)
) -> MessageDraftOut:
    return MessageDraftOut(
        **await service.draft_message(
            session,
            user.id,
            kind=body.kind,
            recipient_name=body.recipient_name,
            recipient_role=body.recipient_role,
            company=body.company,
            context=body.context,
        )
    )


@router.post("/publish", response_model=ApprovalOut, status_code=201)
async def publish(
    body: PublishRequest, user: m.User = Depends(current_user), session: AsyncSession = Depends(get_db)
) -> m.ActionApproval:
    return await service.request_publish(session, user.id, text=body.text, preview_channel="web")


@router.post("/messages", response_model=ApprovalOut, status_code=201)
async def send_message(
    body: SendMessageRequest, user: m.User = Depends(current_user), session: AsyncSession = Depends(get_db)
) -> m.ActionApproval:
    return await service.request_message(session, user.id, recipient=body.recipient, text=body.text, preview_channel="web")
