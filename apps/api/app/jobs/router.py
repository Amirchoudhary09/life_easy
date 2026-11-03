from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.applications.service import create_application
from app.auth.deps import current_user
from app.config import get_settings
from app.core.audit import record_audit
from app.core.errors import NotFound
from app.core.pagination import Page
from app.db import models as m
from app.db.session import get_db
from app.jobs.matching import search_jobs
from app.jobs.schemas import IngestRequest, JobOut, JobSummary, MatchOut, MatchStatusUpdate
from app.jobs.sources import BOARD_SOURCES, SEARCH_SOURCES
from app.security.ratelimit import rate_limit
from app.tasks.runner import enqueue

router = APIRouter(prefix="/api/v1", tags=["jobs"])


@router.get("/jobs", response_model=Page[JobSummary])
async def list_jobs(
    query: str | None = Query(default=None, max_length=200),
    location: str | None = Query(default=None, max_length=120),
    remote: bool | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _: m.User = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> Page[JobSummary]:
    rows, total = await search_jobs(session, query=query, location=location, remote=remote, limit=limit, offset=offset)
    return Page(items=[JobSummary.model_validate(r) for r in rows], total=total, limit=limit, offset=offset)


@router.get("/jobs/sources")
async def job_sources(_: m.User = Depends(current_user)) -> dict[str, object]:
    s = get_settings()
    return {
        "boards": [{"provider": p, "token": t} for p, t in s.job_board_list],
        "board_providers": sorted(BOARD_SOURCES),
        "search": {name: src.configured() for name, src in SEARCH_SOURCES.items()},
    }


@router.post("/jobs/ingest", status_code=202, dependencies=[Depends(rate_limit("ingest", 5, 3600))])
async def trigger_ingest(
    body: IngestRequest, user: m.User = Depends(current_user), session: AsyncSession = Depends(get_db)
) -> dict[str, str]:
    await record_audit(session, user_id=user.id, actor="user", event_type="jobs.ingest_requested")
    await session.commit()
    await enqueue("ingest_jobs", sources=body.sources)
    return {"status": "scheduled"}


@router.get("/jobs/{job_id}", response_model=JobOut)
async def read_job(job_id: uuid.UUID, _: m.User = Depends(current_user), session: AsyncSession = Depends(get_db)) -> m.Job:
    job = await session.get(m.Job, job_id)
    if job is None:
        raise NotFound("job not found")
    return job


@router.get("/matches", response_model=list[MatchOut])
async def list_matches(
    status: str | None = Query(default=None, pattern="^(suggested|saved|skipped|applied)$"),
    limit: int = Query(default=50, ge=1, le=200),
    user: m.User = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> list[MatchOut]:
    stmt = select(m.JobMatch, m.Job).join(m.Job, m.Job.id == m.JobMatch.job_id).where(m.JobMatch.user_id == user.id)
    if status:
        stmt = stmt.where(m.JobMatch.status == status)
    else:
        stmt = stmt.where(m.JobMatch.status != "skipped")
    rows = (await session.execute(stmt.order_by(m.JobMatch.score.desc()).limit(limit))).all()
    return [
        MatchOut(
            job=JobSummary.model_validate(job),
            score=float(jm.score),
            explanation=jm.explanation,
            status=jm.status,
            updated_at=jm.updated_at,
        )
        for jm, job in rows
    ]


@router.post("/matches/refresh", status_code=202, dependencies=[Depends(rate_limit("match", 10, 600))])
async def refresh_matches(user: m.User = Depends(current_user)) -> dict[str, str]:
    await enqueue("match_user", user_id=str(user.id))
    return {"status": "scheduled"}


@router.patch("/matches/{job_id}", response_model=MatchOut)
async def update_match(
    job_id: uuid.UUID, body: MatchStatusUpdate, user: m.User = Depends(current_user), session: AsyncSession = Depends(get_db)
) -> MatchOut:
    job = await session.get(m.Job, job_id)
    if job is None:
        raise NotFound("job not found")
    jm = await session.get(m.JobMatch, {"user_id": user.id, "job_id": job_id})
    if jm is None:
        jm = m.JobMatch(user_id=user.id, job_id=job_id, score=0, explanation={"summary": "Added manually."}, status=body.status)
        session.add(jm)
    jm.status = body.status
    jm.updated_at = datetime.now(UTC)
    if body.status == "applied":
        await create_application(session, user.id, job=job, status="applied")
    await record_audit(
        session,
        user_id=user.id,
        actor="user",
        event_type="match.status",
        target_type="job",
        target_id=job_id,
        details={"status": body.status},
    )
    await session.flush()
    return MatchOut(
        job=JobSummary.model_validate(job),
        score=float(jm.score),
        explanation=jm.explanation,
        status=jm.status,
        updated_at=jm.updated_at,
    )
