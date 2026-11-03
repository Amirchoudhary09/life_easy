from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import current_user
from app.core.errors import NotFound
from app.db import models as m
from app.db.session import get_db
from app.resumes import service
from app.resumes.schemas import ResumeOut, TailorOut, TailorRequest
from app.resumes.storage import get_storage
from app.security.ratelimit import rate_limit

router = APIRouter(prefix="/api/v1/resumes", tags=["resumes"])


def _out(r: m.Resume) -> ResumeOut:
    out = ResumeOut.model_validate(r)
    out.has_text = bool(r.text)
    return out


@router.get("", response_model=list[ResumeOut])
async def list_resumes(user: m.User = Depends(current_user), session: AsyncSession = Depends(get_db)) -> list[ResumeOut]:
    rows = (await session.scalars(select(m.Resume).where(m.Resume.user_id == user.id).order_by(m.Resume.created_at.desc()))).all()
    return [_out(r) for r in rows]


@router.post("", response_model=ResumeOut, status_code=201, dependencies=[Depends(rate_limit("upload", 20))])
async def upload_resume(
    file: UploadFile = File(...), user: m.User = Depends(current_user), session: AsyncSession = Depends(get_db)
) -> ResumeOut:
    data = await file.read()
    resume = await service.upload(
        session,
        user.id,
        filename=file.filename or "resume",
        content_type=file.content_type or "application/octet-stream",
        data=data,
    )
    return _out(resume)


@router.get("/{resume_id}", response_model=ResumeOut)
async def read_resume(
    resume_id: uuid.UUID, user: m.User = Depends(current_user), session: AsyncSession = Depends(get_db)
) -> ResumeOut:
    return _out(await service.get_owned(session, user.id, resume_id))


@router.get("/{resume_id}/download")
async def download_resume(
    resume_id: uuid.UUID, user: m.User = Depends(current_user), session: AsyncSession = Depends(get_db)
) -> Response:
    resume = await service.get_owned(session, user.id, resume_id)
    data = await get_storage().get(resume.object_key)
    return Response(
        content=data, media_type=resume.content_type, headers={"Content-Disposition": f'attachment; filename="{resume.filename}"'}
    )


@router.post("/{resume_id}/primary", response_model=ResumeOut)
async def set_primary(
    resume_id: uuid.UUID, user: m.User = Depends(current_user), session: AsyncSession = Depends(get_db)
) -> ResumeOut:
    resume = await service.get_owned(session, user.id, resume_id)
    rows = (await session.scalars(select(m.Resume).where(m.Resume.user_id == user.id))).all()
    for r in rows:
        r.is_primary = r.id == resume.id
    return _out(resume)


@router.delete("/{resume_id}", status_code=204)
async def delete_resume(resume_id: uuid.UUID, user: m.User = Depends(current_user), session: AsyncSession = Depends(get_db)):  # noqa: ANN201
    resume = await service.get_owned(session, user.id, resume_id)
    await get_storage().delete(resume.object_key)
    await session.delete(resume)


@router.post("/tailor", response_model=TailorOut, dependencies=[Depends(rate_limit("tailor", 20))])
async def tailor_resume(
    body: TailorRequest, user: m.User = Depends(current_user), session: AsyncSession = Depends(get_db)
) -> TailorOut:
    job = await session.get(m.Job, body.job_id)
    if job is None:
        raise NotFound("job not found")
    resume = (
        await service.get_owned(session, user.id, body.resume_id)
        if body.resume_id
        else await service.primary_resume(session, user.id)
    )
    if resume is None:
        raise NotFound("upload a resume first")
    tailored, ats = await service.tailor(session, user.id, job=job, resume=resume, notes=body.notes)
    return TailorOut(resume=_out(tailored), markdown=tailored.text or "", ats=ats)
