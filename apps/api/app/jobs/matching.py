"""Profile <-> job matching with explanations.

Two stages: embeddings give a candidate list, then rules (title, skills,
location, recency, preferences) and the LLM (top results only) produce a
0-100 score and a plain-language explanation the user can check.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings import get_embeddings, nearest_jobs
from app.ai.llm import get_llm, untrusted
from app.ai.usage import charge, ensure_within_limit
from app.core.errors import LimitExceeded, ProviderError
from app.core.logging import get_logger
from app.db import models as m
from app.db.session import get_session_factory
from app.resumes.service import primary_resume

log = get_logger(__name__)
_WORD = re.compile(r"[a-z0-9+#.]{2,}")
STOP = {"and", "the", "for", "with", "of", "in", "to", "a", "an", "or", "at", "on", "senior", "junior", "sr", "jr", "ii", "iii"}
LLM_EXPLAIN_TOP = 10

EXPLAIN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {"type": "string", "description": "two sentences on fit, for the candidate"},
        "strengths": {"type": "array", "items": {"type": "string"}},
        "gaps": {"type": "array", "items": {"type": "string"}},
        "recommended": {"type": "boolean"},
    },
    "required": ["summary", "strengths", "gaps", "recommended"],
}


def tokens(text: str | None) -> set[str]:
    return {t for t in _WORD.findall((text or "").lower()) if t not in STOP}


async def profile_text(session: AsyncSession, user_id: uuid.UUID) -> tuple[m.Profile | None, str]:
    profile = await session.get(m.Profile, user_id)
    if profile is None:
        return None, ""
    prefs = profile.preferences or {}
    parts = [profile.headline or "", profile.summary or "", " ".join(profile.skills or []), " ".join(prefs.get("titles", []))]
    resume = await primary_resume(session, user_id)
    if resume is not None:
        parsed = resume.parsed or {}
        parts.append(" ".join(parsed.get("skills", [])[:60]))
        for exp in parsed.get("experience", [])[:6]:
            if isinstance(exp, dict):
                parts.append(f"{exp.get('title', '')} {exp.get('company', '')} " + " ".join(exp.get("highlights", [])[:4]))
        if not parts[0] and resume.text:
            parts.append(resume.text[:3000])
    return profile, "\n".join(p for p in parts if p).strip()


def _location_ok(job: m.Job, prefs: dict[str, Any], profile_location: str | None) -> bool:
    mode = prefs.get("remote", "any")
    wanted = [str(loc).lower() for loc in prefs.get("locations", []) if loc] or (
        [profile_location.lower()] if profile_location else []
    )
    job_loc = (job.location or "").lower()
    if mode == "remote":
        return bool(job.remote) or "remote" in job_loc
    if job.remote and mode in ("any", "hybrid"):
        return True
    if not wanted:
        return True
    return any(w and (w in job_loc or job_loc in w) for w in wanted)


def rule_score(
    job: m.Job, sim_norm: float, *, prefs: dict[str, Any], skills: list[str], profile_location: str | None
) -> tuple[float, dict[str, Any]]:
    title_pref = tokens(" ".join(prefs.get("titles", [])))
    job_title = tokens(job.title)
    title_score = len(title_pref & job_title) / max(1, min(len(title_pref), 3)) if title_pref else 0.5
    title_score = min(1.0, title_score)
    desc_tokens = tokens(job.description) | job_title
    skill_set = {s.lower() for s in skills}
    matched = sorted(s for s in skill_set if s and (s in desc_tokens or s in (job.description or "").lower()))
    skill_score = min(1.0, len(matched) / max(1, min(len(skill_set), 8))) if skill_set else 0.5
    days = (datetime.now(UTC) - job.posted_at).days if job.posted_at else 30
    recency = 1.0 if days <= 7 else 0.6 if days <= 30 else 0.3
    loc_ok = _location_ok(job, prefs, profile_location)
    emp = prefs.get("employment_types") or []
    emp_ok = not job.employment_type or not emp or job.employment_type in emp
    raw = 0.5 * sim_norm + 0.2 * title_score + 0.2 * skill_score + 0.1 * recency
    score = 100.0 * raw * (1.0 if loc_ok else 0.6) * (1.0 if emp_ok else 0.7)
    explanation = {
        "summary": f"{len(matched)} of your skills appear in this posting."
        if skill_set
        else "Add skills to your profile for a better match.",
        "strengths": [f"Skill match: {s}" for s in matched[:6]],
        "gaps": [] if loc_ok else [f"Location {job.location or 'unknown'} is outside your preferences"],
        "location_ok": loc_ok,
        "employment_type_ok": emp_ok,
        "similarity": round(sim_norm, 3),
        "recommended": score >= 60,
    }
    return round(min(100.0, score), 2), explanation


async def refresh_matches_for_user(user_id: uuid.UUID, *, limit: int = 50, explain: bool = True) -> dict[str, Any]:
    async with get_session_factory()() as session:
        profile, text = await profile_text(session, user_id)
        if profile is None or not text:
            return {"status": "no_profile", "matched": 0}
        emb = get_embeddings()
        if profile.embedding is None:
            profile.embedding = (await emb.embed([text[:8000]]))[0]
        prefs = profile.preferences or {}
        exclude = {c.lower() for c in prefs.get("exclude_companies", [])}
        candidates = await nearest_jobs(session, profile.embedding, limit=300)
        candidates = [(j, s) for j, s in candidates if j.company.lower() not in exclude]
        if not candidates:
            await session.commit()
            return {"status": "no_jobs", "matched": 0}
        sims = [s for _, s in candidates]
        lo, hi = min(sims), max(sims)
        scored: list[tuple[m.Job, float, dict[str, Any]]] = []
        for job, sim in candidates:
            sim_norm = (sim - lo) / (hi - lo) if hi > lo else 0.5
            score, expl = rule_score(
                job, sim_norm, prefs=prefs, skills=list(profile.skills or []), profile_location=profile.location
            )
            scored.append((job, score, expl))
        scored.sort(key=lambda t: t[1], reverse=True)
        top = scored[:limit]
        if explain:
            await _explain_with_llm(session, user_id, text, top[:LLM_EXPLAIN_TOP])
        existing = {
            jm.job_id: jm
            for jm in (
                await session.scalars(
                    select(m.JobMatch).where(m.JobMatch.user_id == user_id, m.JobMatch.job_id.in_([j.id for j, _, _ in top]))
                )
            ).all()
        }
        for job, score, expl in top:
            jm = existing.get(job.id)
            if jm is None:
                session.add(m.JobMatch(user_id=user_id, job_id=job.id, score=score, explanation=expl, status="suggested"))
            else:
                jm.score = score
                jm.explanation = {**jm.explanation, **expl}
        await session.commit()
        return {"status": "ok", "matched": len(top), "best": top[0][1] if top else 0}


async def _explain_with_llm(
    session: AsyncSession, user_id: uuid.UUID, profile: str, items: list[tuple[m.Job, float, dict[str, Any]]]
) -> None:
    llm = get_llm()
    system = (
        "You assess job fit for a candidate. Be specific and honest: name the strengths that are actually in the "
        "candidate profile and the gaps the posting asks for. Never invent candidate experience."
    )
    for job, _, expl in items:
        try:
            await ensure_within_limit(session, user_id)
            prompt = (
                "CANDIDATE PROFILE:\n"
                + untrusted(profile[:6000], "candidate_profile")
                + "\n\nJOB:\n"
                + untrusted(
                    f"{job.title} at {job.company} ({job.location or 'location unknown'})\n{(job.description or '')[:6000]}",
                    "job_posting",
                )
            )
            data = await llm.json(system=system, prompt=prompt, schema=EXPLAIN_SCHEMA, max_tokens=600)
            await charge(session, user_id, "llm")
            if data.get("summary"):
                expl["summary"] = str(data["summary"])[:1000]
            if data.get("strengths"):
                expl["strengths"] = [str(s)[:200] for s in data["strengths"]][:8]
            if data.get("gaps"):
                expl["gaps"] = [str(s)[:200] for s in data["gaps"]][:8] + expl.get("gaps", [])
            if "recommended" in data:
                expl["recommended"] = bool(data["recommended"])
        except (LimitExceeded, ProviderError) as exc:
            log.warning("explanation skipped", reason=str(exc))
            break


async def search_jobs(
    session: AsyncSession, *, query: str | None, location: str | None, remote: bool | None, limit: int, offset: int
) -> tuple[list[m.Job], int]:
    stmt = select(m.Job).where(m.Job.is_active.is_(True))
    if query:
        like = f"%{query.strip()}%"
        stmt = stmt.where((m.Job.title.ilike(like)) | (m.Job.company.ilike(like)) | (m.Job.description.ilike(like)))
    if location:
        stmt = stmt.where(m.Job.location.ilike(f"%{location.strip()}%"))
    if remote is not None:
        stmt = stmt.where(m.Job.remote.is_(remote))
    from sqlalchemy import func

    total = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = (
        await session.scalars(
            stmt.order_by(m.Job.posted_at.desc().nullslast(), m.Job.fetched_at.desc()).limit(limit).offset(offset)
        )
    ).all()
    return list(rows), int(total)
