from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.applications import service
from app.applications.schemas import (
    ApplicationCreate,
    ApplicationOut,
    ApplicationUpdate,
    EventOut,
    FollowUpCreate,
    FollowUpOut,
    InterviewCreate,
    InterviewOut,
    InterviewUpdate,
    StatsOut,
)
from app.auth.deps import current_user
from app.core.errors import NotFound
from app.core.pagination import Page
from app.db import models as m
from app.db.session import get_db

router = APIRouter(prefix="/api/v1", tags=["applications"])


@router.get("/applications", response_model=Page[ApplicationOut])
async def list_applications(
    status: str | None = Query(default=None, max_length=20),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: m.User = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> Page[ApplicationOut]:
    rows, total = await service.list_applications(session, user.id, status=status, limit=limit, offset=offset)
    return Page(items=[ApplicationOut.model_validate(r) for r in rows], total=total, limit=limit, offset=offset)


@router.get("/applications/stats", response_model=StatsOut)
async def application_stats(user: m.User = Depends(current_user), session: AsyncSession = Depends(get_db)) -> StatsOut:
    return StatsOut(**await service.stats(session, user.id))


@router.post("/applications", response_model=ApplicationOut, status_code=201)
async def create_application(
    body: ApplicationCreate, user: m.User = Depends(current_user), session: AsyncSession = Depends(get_db)
) -> m.Application:
    job = await session.get(m.Job, body.job_id) if body.job_id else None
    if body.job_id and job is None:
        raise NotFound("job not found")
    return await service.create_application(
        session,
        user.id,
        job=job,
        company=body.company,
        title=body.title,
        status=body.status,
        source_url=body.source_url,
        notes=body.notes,
    )


@router.get("/applications/{application_id}", response_model=ApplicationOut)
async def read_application(
    application_id: uuid.UUID, user: m.User = Depends(current_user), session: AsyncSession = Depends(get_db)
) -> m.Application:
    return await service.get_owned(session, user.id, application_id)


@router.patch("/applications/{application_id}", response_model=ApplicationOut)
async def update_application(
    application_id: uuid.UUID,
    body: ApplicationUpdate,
    user: m.User = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> m.Application:
    app = await service.get_owned(session, user.id, application_id)
    if body.status is not None:
        await service.set_status(session, user.id, app, body.status, note=body.note)
    if body.notes is not None:
        app.notes = body.notes
    if "next_follow_up_at" in body.model_fields_set:
        app.next_follow_up_at = body.next_follow_up_at
    if body.resume_id is not None:
        resume = await session.get(m.Resume, body.resume_id)
        if resume is None or resume.user_id != user.id:
            raise NotFound("resume not found")
        app.resume_id = resume.id
    await session.flush()
    return app


@router.delete("/applications/{application_id}", status_code=204)
async def delete_application(
    application_id: uuid.UUID, user: m.User = Depends(current_user), session: AsyncSession = Depends(get_db)
):  # noqa: ANN201 - 204, no body
    app = await service.get_owned(session, user.id, application_id)
    await session.delete(app)


@router.get("/applications/{application_id}/events", response_model=list[EventOut])
async def application_events(
    application_id: uuid.UUID, user: m.User = Depends(current_user), session: AsyncSession = Depends(get_db)
) -> list[m.ApplicationEvent]:
    app = await service.get_owned(session, user.id, application_id)
    rows = (
        await session.scalars(
            select(m.ApplicationEvent).where(m.ApplicationEvent.application_id == app.id).order_by(m.ApplicationEvent.created_at)
        )
    ).all()
    return list(rows)


@router.post("/applications/{application_id}/interviews", response_model=InterviewOut, status_code=201)
async def add_interview(
    application_id: uuid.UUID,
    body: InterviewCreate,
    user: m.User = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> m.Interview:
    app = await service.get_owned(session, user.id, application_id)
    return await service.add_interview(
        session, user.id, app, scheduled_at=body.scheduled_at, kind=body.kind, location=body.location, notes=body.notes
    )


@router.get("/interviews", response_model=list[InterviewOut])
async def list_interviews(
    upcoming: bool = True, user: m.User = Depends(current_user), session: AsyncSession = Depends(get_db)
) -> list[m.Interview]:
    stmt = select(m.Interview).where(m.Interview.user_id == user.id)
    if upcoming:
        stmt = stmt.where(m.Interview.scheduled_at >= datetime.now(UTC))
    return list((await session.scalars(stmt.order_by(m.Interview.scheduled_at))).all())


@router.patch("/interviews/{interview_id}", response_model=InterviewOut)
async def update_interview(
    interview_id: uuid.UUID,
    body: InterviewUpdate,
    user: m.User = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> m.Interview:
    interview = await session.get(m.Interview, interview_id)
    if interview is None or interview.user_id != user.id:
        raise NotFound("interview not found")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(interview, key, value)
    await session.flush()
    return interview


@router.post("/applications/{application_id}/follow-ups", response_model=FollowUpOut, status_code=201)
async def add_follow_up(
    application_id: uuid.UUID,
    body: FollowUpCreate,
    user: m.User = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> m.FollowUp:
    app = await service.get_owned(session, user.id, application_id)
    return await service.schedule_follow_up(session, user.id, app, due_at=body.due_at)


@router.get("/follow-ups", response_model=list[FollowUpOut])
async def list_follow_ups(user: m.User = Depends(current_user), session: AsyncSession = Depends(get_db)) -> list[m.FollowUp]:
    rows = (
        await session.scalars(
            select(m.FollowUp)
            .where(m.FollowUp.user_id == user.id, m.FollowUp.status.in_(("pending", "drafted")))
            .order_by(m.FollowUp.due_at)
        )
    ).all()
    return list(rows)
