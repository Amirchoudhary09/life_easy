from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings import get_embeddings
from app.ai.llm import get_llm, untrusted
from app.ai.usage import charge, ensure_within_limit
from app.core.audit import record_audit
from app.core.errors import AppError, NotFound
from app.db import models as m
from app.db.session import get_session_factory
from app.resumes.parser import extract_text, parse_structured
from app.resumes.storage import get_storage, safe_key
from app.tasks.runner import enqueue

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
ALLOWED_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
    "text/markdown",
}


async def upload(session: AsyncSession, user_id: uuid.UUID, *, filename: str, content_type: str, data: bytes) -> m.Resume:
    if len(data) == 0 or len(data) > MAX_UPLOAD_BYTES:
        raise AppError("resume must be between 1 byte and 5 MB")
    lowered = filename.lower()
    if content_type not in ALLOWED_TYPES and not lowered.endswith((".pdf", ".docx", ".txt", ".md")):
        raise AppError("only PDF, DOCX, TXT or MD resumes are accepted")
    key = safe_key("resumes", str(user_id), f"{uuid.uuid4().hex}-{filename}")
    await get_storage().put(key, data, content_type)
    first = await session.scalar(select(m.Resume.id).where(m.Resume.user_id == user_id).limit(1)) is None
    resume = m.Resume(
        user_id=user_id,
        filename=filename[:255],
        content_type=content_type,
        object_key=key,
        size_bytes=len(data),
        is_primary=first,
    )
    session.add(resume)
    await session.flush()
    await record_audit(
        session, user_id=user_id, actor="user", event_type="resume.upload", target_type="resume", target_id=resume.id
    )
    await session.commit()
    await enqueue("parse_resume", resume_id=str(resume.id))
    return resume


async def parse_and_store(resume_id: uuid.UUID) -> dict[str, Any]:
    async with get_session_factory()() as session:
        resume = await session.get(m.Resume, resume_id)
        if resume is None:
            return {"status": "missing"}
        data = await get_storage().get(resume.object_key)
        text = extract_text(data, resume.content_type, resume.filename)
        resume.text = text
        if text:
            llm = get_llm()
            await ensure_within_limit(session, resume.user_id)
            parsed = await parse_structured(llm, text)
            await charge(session, resume.user_id, "llm")
            resume.parsed = parsed
            resume.embedding = (await get_embeddings().embed([text[:8000]]))[0]
            profile = await session.get(m.Profile, resume.user_id)
            if profile is not None:
                if not profile.skills and parsed.get("skills"):
                    profile.skills = parsed["skills"][:100]
                if not profile.headline and parsed.get("headline"):
                    profile.headline = str(parsed["headline"])[:200]
                if not profile.summary and parsed.get("summary"):
                    profile.summary = str(parsed["summary"])[:4000]
                if profile.experience_years is None and parsed.get("years_experience"):
                    try:
                        profile.experience_years = float(parsed["years_experience"])
                    except (TypeError, ValueError):
                        pass
                profile.embedding = None
        await session.commit()
    await enqueue("match_user", user_id=str(resume.user_id))
    return {"status": "parsed", "chars": len(text)}


async def get_owned(session: AsyncSession, user_id: uuid.UUID, resume_id: uuid.UUID) -> m.Resume:
    resume = await session.get(m.Resume, resume_id)
    if resume is None or resume.user_id != user_id:
        raise NotFound("resume not found")
    return resume


async def primary_resume(session: AsyncSession, user_id: uuid.UUID) -> m.Resume | None:
    stmt = (
        select(m.Resume)
        .where(m.Resume.user_id == user_id, m.Resume.tailored_for_job_id.is_(None))
        .order_by(m.Resume.is_primary.desc(), m.Resume.created_at.desc())
        .limit(1)
    )
    return await session.scalar(stmt)


TAILOR_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "markdown": {"type": "string", "description": "the full tailored resume in Markdown"},
        "ats": {
            "type": "object",
            "properties": {
                "matched_keywords": {"type": "array", "items": {"type": "string"}},
                "missing_keywords": {"type": "array", "items": {"type": "string"}},
                "score": {"type": "integer", "description": "0-100 keyword coverage"},
                "notes": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
    "required": ["markdown", "ats"],
}


async def tailor(
    session: AsyncSession, user_id: uuid.UUID, *, job: m.Job, resume: m.Resume, notes: str | None
) -> tuple[m.Resume, dict[str, Any]]:
    """Rewrite the resume for one job. Facts stay the same; only emphasis, order and wording change."""
    if not resume.text:
        raise AppError("resume text is not available yet; try again in a moment")
    await ensure_within_limit(session, user_id)
    llm = get_llm()
    system = (
        "You are a resume editor. Rewrite the candidate's resume so it best fits the job while staying truthful: "
        "never add employers, titles, dates, degrees, tools or achievements that are not in the original. "
        "Reorder and reword, mirror the job's vocabulary where the candidate genuinely has the skill, "
        "and keep it to one or two pages. Report ATS keyword coverage."
    )
    prompt = (
        f"JOB TITLE: {job.title}\nCOMPANY: {job.company}\n"
        + untrusted(job.description or "", "job_description")
        + "\n\nORIGINAL RESUME:\n"
        + untrusted(resume.text, "resume")
        + (f"\n\nCANDIDATE NOTES: {notes}" if notes else "")
    )
    data = await llm.json(system=system, prompt=prompt, schema=TAILOR_SCHEMA, max_tokens=4000)
    await charge(session, user_id, "llm")
    markdown = str(data.get("markdown") or "")
    key = safe_key("resumes", str(user_id), f"tailored-{job.id.hex[:8]}-{uuid.uuid4().hex[:6]}.md")
    await get_storage().put(key, markdown.encode("utf-8"), "text/markdown")
    tailored = m.Resume(
        user_id=user_id,
        filename=f"{resume.filename.rsplit('.', 1)[0]} - {job.company}.md"[:255],
        content_type="text/markdown",
        object_key=key,
        size_bytes=len(markdown.encode("utf-8")),
        text=markdown,
        parsed={"ats": data.get("ats", {}), "based_on": str(resume.id)},
        tailored_for_job_id=job.id,
    )
    session.add(tailored)
    await session.flush()
    await record_audit(
        session,
        user_id=user_id,
        actor="agent",
        event_type="resume.tailor",
        target_type="resume",
        target_id=tailored.id,
        details={"job_id": str(job.id)},
    )
    return tailored, data.get("ats", {})
