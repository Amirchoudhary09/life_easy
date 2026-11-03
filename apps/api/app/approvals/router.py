from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.approvals import service
from app.approvals.schemas import ApprovalOut, ApproveRequest, EditRequest, RejectRequest
from app.auth.deps import current_user
from app.db import models as m
from app.db.session import get_db

router = APIRouter(prefix="/api/v1/approvals", tags=["approvals"])


@router.get("", response_model=list[ApprovalOut])
async def list_approvals(
    status: str | None = Query(default=None, pattern="^(pending|approved|rejected|executing|executed|failed|expired)$"),
    limit: int = Query(default=50, ge=1, le=200),
    user: m.User = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> list[m.ActionApproval]:
    return await service.list_for_user(session, user.id, status=status, limit=limit)


@router.get("/{approval_id}", response_model=ApprovalOut)
async def read_approval(
    approval_id: uuid.UUID, user: m.User = Depends(current_user), session: AsyncSession = Depends(get_db)
) -> m.ActionApproval:
    return await service.get_owned(session, user.id, approval_id)


@router.post("/{approval_id}/approve", response_model=ApprovalOut)
async def approve(
    approval_id: uuid.UUID,
    body: ApproveRequest,
    user: m.User = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> m.ActionApproval:
    approval = await service.get_owned(session, user.id, approval_id)
    return await service.approve(session, user.id, approval, expected_hash=body.content_hash, via="web")


@router.post("/{approval_id}/reject", response_model=ApprovalOut)
async def reject(
    approval_id: uuid.UUID,
    body: RejectRequest,
    user: m.User = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> m.ActionApproval:
    approval = await service.get_owned(session, user.id, approval_id)
    return await service.reject(session, user.id, approval, via="web", reason=body.reason)


@router.post("/{approval_id}/edit", response_model=ApprovalOut, status_code=201)
async def edit(
    approval_id: uuid.UUID,
    body: EditRequest,
    user: m.User = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> m.ActionApproval:
    approval = await service.get_owned(session, user.id, approval_id)
    return await service.edit(
        session, user.id, approval, subject=body.subject, body=body.body, destination=body.destination, via="web"
    )
