"""Agent tools. Safe tools act immediately; `request_*` tools only create approval previews."""

from __future__ import annotations

import re
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.llm import ToolSpec, untrusted
from app.db import models as m

ToolHandler = Callable[["ToolContext", dict[str, Any]], Awaitable[Any]]


@dataclass
class ToolContext:
    session: AsyncSession
    user: m.User
    channel: str
    approvals: list[m.ActionApproval] = field(default_factory=list)
    tool_calls_made: list[str] = field(default_factory=list)


_specs: list[ToolSpec] = []
_handlers: dict[str, ToolHandler] = {}


def tool(name: str, description: str, schema: dict[str, Any]) -> Callable[[ToolHandler], ToolHandler]:
    def deco(fn: ToolHandler) -> ToolHandler:
        _specs.append(ToolSpec(name=name, description=description, input_schema={"type": "object", **schema}))
        _handlers[name] = fn
        return fn

    return deco


def specs() -> list[ToolSpec]:
    return list(_specs)


def handler(name: str) -> ToolHandler | None:
    return _handlers.get(name)


def _job_row(job: m.Job, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    row = {
        "job_id": str(job.id),
        "title": job.title,
        "company": job.company,
        "location": job.location,
        "remote": job.remote,
        "employment_type": job.employment_type,
        "salary": job.salary_text,
        "posted_at": job.posted_at.date().isoformat() if job.posted_at else None,
        "apply_url": job.apply_url,
    }
    if extra:
        row.update(extra)
    return row


def _uuid(value: Any) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except ValueError as exc:
        raise ValueError(f"'{value}' is not a valid id") from exc


# --- jobs ---------------------------------------------------------------------


@tool(
    "search_jobs",
    "Search the job database by keywords, optional location and remote filter. Returns up to `limit` jobs with ids and apply links.",
    {
        "properties": {
            "query": {"type": "string"},
            "location": {"type": "string"},
            "remote": {"type": "boolean"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 20},
        },
        "required": ["query"],
    },
)
async def search_jobs(ctx: ToolContext, args: dict[str, Any]) -> Any:
    from app.jobs.matching import search_jobs as _search

    rows, total = await _search(
        ctx.session,
        query=args.get("query"),
        location=args.get("location"),
        remote=args.get("remote"),
        limit=int(args.get("limit", 8)),
        offset=0,
    )
    return {"total": total, "jobs": [_job_row(j, {"description_excerpt": (j.description or "")[:300]}) for j in rows]}


@tool(
    "get_matches",
    "The user's ranked job matches with scores and explanations. status: suggested|saved|applied (default suggested).",
    {
        "properties": {
            "status": {"type": "string", "enum": ["suggested", "saved", "applied", "skipped"]},
            "limit": {"type": "integer", "minimum": 1, "maximum": 20},
        }
    },
)
async def get_matches(ctx: ToolContext, args: dict[str, Any]) -> Any:
    status = args.get("status", "suggested")
    stmt = (
        select(m.JobMatch, m.Job)
        .join(m.Job, m.Job.id == m.JobMatch.job_id)
        .where(m.JobMatch.user_id == ctx.user.id, m.JobMatch.status == status)
    )
    rows = (await ctx.session.execute(stmt.order_by(m.JobMatch.score.desc()).limit(int(args.get("limit", 8))))).all()
    if not rows and status == "suggested":
        return {
            "matches": [],
            "hint": "No matches yet. Ask the user to upload a resume or set preferences, then call refresh_matches.",
        }
    return {
        "matches": [
            _job_row(
                job,
                {
                    "score": float(jm.score),
                    "why": jm.explanation.get("summary", ""),
                    "strengths": jm.explanation.get("strengths", [])[:3],
                    "gaps": jm.explanation.get("gaps", [])[:3],
                },
            )
            for jm, job in rows
        ]
    }


@tool(
    "refresh_matches",
    "Recompute the user's job matches from their profile and resume. Use after preferences or resume changed.",
    {"properties": {}},
)
async def refresh_matches(ctx: ToolContext, args: dict[str, Any]) -> Any:
    from app.jobs.matching import refresh_matches_for_user

    await ctx.session.commit()
    return await refresh_matches_for_user(ctx.user.id, limit=30)


@tool(
    "set_job_status",
    "Save, skip, or mark a job as applied. Marking applied also creates a tracker entry.",
    {
        "properties": {"job_id": {"type": "string"}, "status": {"type": "string", "enum": ["saved", "skipped", "applied"]}},
        "required": ["job_id", "status"],
    },
)
async def set_job_status(ctx: ToolContext, args: dict[str, Any]) -> Any:
    from app.applications.service import create_application

    job = await ctx.session.get(m.Job, _uuid(args["job_id"]))
    if job is None:
        return {"error": "job not found"}
    jm = await ctx.session.get(m.JobMatch, {"user_id": ctx.user.id, "job_id": job.id})
    if jm is None:
        jm = m.JobMatch(user_id=ctx.user.id, job_id=job.id, score=0, explanation={})
        ctx.session.add(jm)
    jm.status = args["status"]
    if args["status"] == "applied":
        app = await create_application(ctx.session, ctx.user.id, job=job, status="applied", source="agent")
        return {
            "ok": True,
            "application_id": str(app.id),
            "follow_up_at": app.next_follow_up_at.isoformat() if app.next_follow_up_at else None,
        }
    return {"ok": True}


# --- profile ------------------------------------------------------------------


@tool("get_profile", "The user's profile, preferences and primary resume summary.", {"properties": {}})
async def get_profile(ctx: ToolContext, args: dict[str, Any]) -> Any:
    from app.resumes.service import primary_resume

    profile = await ctx.session.get(m.Profile, ctx.user.id)
    resume = await primary_resume(ctx.session, ctx.user.id)
    return {
        "display_name": ctx.user.display_name,
        "headline": profile.headline if profile else None,
        "location": profile.location if profile else None,
        "experience_years": float(profile.experience_years) if profile and profile.experience_years is not None else None,
        "skills": (profile.skills if profile else []) or [],
        "preferences": (profile.preferences if profile else {}) or {},
        "resume": {
            "id": str(resume.id),
            "filename": resume.filename,
            "parsed": {
                k: v for k, v in (resume.parsed or {}).items() if k in ("headline", "summary", "years_experience", "experience")
            },
        }
        if resume
        else None,
    }


@tool(
    "update_preferences",
    "Update job preferences. Only pass fields the user stated.",
    {
        "properties": {
            "titles": {"type": "array", "items": {"type": "string"}},
            "locations": {"type": "array", "items": {"type": "string"}},
            "remote": {"type": "string", "enum": ["any", "remote", "onsite", "hybrid"]},
            "salary_min": {"type": "integer"},
            "currency": {"type": "string"},
            "employment_types": {"type": "array", "items": {"type": "string"}},
            "exclude_companies": {"type": "array", "items": {"type": "string"}},
            "skills": {"type": "array", "items": {"type": "string"}},
            "headline": {"type": "string"},
            "location": {"type": "string"},
        }
    },
)
async def update_preferences(ctx: ToolContext, args: dict[str, Any]) -> Any:
    profile = await ctx.session.get(m.Profile, ctx.user.id)
    if profile is None:
        profile = m.Profile(user_id=ctx.user.id)
        ctx.session.add(profile)
    prefs = dict(profile.preferences or {})
    for key in ("titles", "locations", "remote", "salary_min", "currency", "employment_types", "exclude_companies"):
        if key in args and args[key] is not None:
            prefs[key] = args[key]
    profile.preferences = prefs
    for key in ("skills", "headline", "location"):
        if args.get(key):
            setattr(profile, key, args[key])
    profile.embedding = None
    await ctx.session.flush()
    return {"ok": True, "preferences": prefs}


# --- tracker ------------------------------------------------------------------


@tool(
    "get_stats",
    "Tracker summary: counts by status, applications this week, upcoming interviews, follow-ups due.",
    {"properties": {}},
)
async def get_stats(ctx: ToolContext, args: dict[str, Any]) -> Any:
    from app.applications.service import stats

    return await stats(ctx.session, ctx.user.id)


@tool(
    "list_applications",
    "List tracked applications, optionally filtered by status.",
    {"properties": {"status": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 50}}},
)
async def list_applications(ctx: ToolContext, args: dict[str, Any]) -> Any:
    from app.applications.service import list_applications as _list

    rows, total = await _list(ctx.session, ctx.user.id, status=args.get("status"), limit=int(args.get("limit", 15)), offset=0)
    return {
        "total": total,
        "applications": [
            {
                "application_id": str(a.id),
                "company": a.company,
                "title": a.title,
                "status": a.status,
                "applied_at": a.applied_at.date().isoformat() if a.applied_at else None,
                "next_follow_up_at": a.next_follow_up_at.date().isoformat() if a.next_follow_up_at else None,
                "notes": (a.notes or "")[:200],
            }
            for a in rows
        ],
    }


@tool(
    "add_application",
    "Track an application the user made outside Life Easy.",
    {
        "properties": {
            "company": {"type": "string"},
            "title": {"type": "string"},
            "status": {"type": "string", "enum": ["planned", "applied", "screening", "interview", "offer"]},
            "url": {"type": "string"},
            "notes": {"type": "string"},
        },
        "required": ["company", "title"],
    },
)
async def add_application(ctx: ToolContext, args: dict[str, Any]) -> Any:
    from app.applications.service import create_application

    app = await create_application(
        ctx.session,
        ctx.user.id,
        company=args["company"],
        title=args["title"],
        status=args.get("status", "applied"),
        source_url=args.get("url"),
        notes=args.get("notes"),
        source="agent",
    )
    return {"application_id": str(app.id), "status": app.status}


@tool(
    "update_application",
    "Change an application's status or add a note.",
    {
        "properties": {
            "application_id": {"type": "string"},
            "status": {
                "type": "string",
                "enum": ["planned", "applied", "screening", "interview", "offer", "accepted", "rejected", "withdrawn"],
            },
            "note": {"type": "string"},
        },
        "required": ["application_id"],
    },
)
async def update_application(ctx: ToolContext, args: dict[str, Any]) -> Any:
    from app.applications.service import get_owned, set_status

    app = await get_owned(ctx.session, ctx.user.id, _uuid(args["application_id"]))
    if args.get("status"):
        await set_status(ctx.session, ctx.user.id, app, args["status"], note=args.get("note"), source="agent")
    elif args.get("note"):
        app.notes = ((app.notes or "") + "\n" + args["note"]).strip()
    return {"ok": True, "status": app.status}


@tool(
    "schedule_follow_up",
    "Schedule a follow-up reminder for an application N days from now.",
    {
        "properties": {"application_id": {"type": "string"}, "days": {"type": "integer", "minimum": 1, "maximum": 60}},
        "required": ["application_id", "days"],
    },
)
async def schedule_follow_up(ctx: ToolContext, args: dict[str, Any]) -> Any:
    from app.applications.service import get_owned
    from app.applications.service import schedule_follow_up as _schedule

    app = await get_owned(ctx.session, ctx.user.id, _uuid(args["application_id"]))
    fu = await _schedule(ctx.session, ctx.user.id, app, due_at=datetime.now(UTC) + timedelta(days=int(args["days"])))
    return {"ok": True, "due_at": fu.due_at.isoformat()}


@tool(
    "add_interview",
    "Record an interview for an application. scheduled_at is ISO 8601 with timezone.",
    {
        "properties": {
            "application_id": {"type": "string"},
            "scheduled_at": {"type": "string"},
            "kind": {"type": "string"},
            "location": {"type": "string"},
            "notes": {"type": "string"},
        },
        "required": ["application_id", "scheduled_at"],
    },
)
async def add_interview(ctx: ToolContext, args: dict[str, Any]) -> Any:
    from app.applications.service import add_interview as _add
    from app.applications.service import get_owned

    app = await get_owned(ctx.session, ctx.user.id, _uuid(args["application_id"]))
    when = datetime.fromisoformat(str(args["scheduled_at"]).replace("Z", "+00:00"))
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    interview = await _add(
        ctx.session,
        ctx.user.id,
        app,
        scheduled_at=when,
        kind=args.get("kind", "interview"),
        location=args.get("location"),
        notes=args.get("notes"),
    )
    return {"ok": True, "interview_id": str(interview.id), "scheduled_at": interview.scheduled_at.isoformat()}


@tool("list_interviews", "Upcoming interviews.", {"properties": {}})
async def list_interviews(ctx: ToolContext, args: dict[str, Any]) -> Any:
    stmt = (
        select(m.Interview, m.Application)
        .join(m.Application, m.Application.id == m.Interview.application_id)
        .where(m.Interview.user_id == ctx.user.id, m.Interview.scheduled_at >= datetime.now(UTC))
        .order_by(m.Interview.scheduled_at)
        .limit(20)
    )
    rows = (await ctx.session.execute(stmt)).all()
    return {
        "interviews": [
            {
                "interview_id": str(i.id),
                "application_id": str(a.id),
                "company": a.company,
                "title": a.title,
                "scheduled_at": i.scheduled_at.isoformat(),
                "kind": i.kind,
                "location": i.location,
            }
            for i, a in rows
        ]
    }


# --- email / linkedin (drafts are safe; request_* create approvals) -------------


@tool(
    "draft_email",
    "Draft a career email (not sent). purpose: application|follow_up|recruiter_outreach|thank_you|custom.",
    {
        "properties": {
            "purpose": {"type": "string"},
            "to_name": {"type": "string"},
            "context": {"type": "string"},
            "tone": {"type": "string", "enum": ["professional", "warm", "concise"]},
            "application_id": {"type": "string"},
            "job_id": {"type": "string"},
        },
        "required": ["purpose", "context"],
    },
)
async def draft_email(ctx: ToolContext, args: dict[str, Any]) -> Any:
    from app.email.service import draft_email as _draft

    application = await ctx.session.get(m.Application, _uuid(args["application_id"])) if args.get("application_id") else None
    if application is not None and application.user_id != ctx.user.id:
        application = None
    job = await ctx.session.get(m.Job, _uuid(args["job_id"])) if args.get("job_id") else None
    return await _draft(
        ctx.session,
        ctx.user.id,
        purpose=args.get("purpose", "custom"),
        to_name=args.get("to_name"),
        context=args.get("context", ""),
        tone=args.get("tone", "professional"),
        application=application,
        job=job,
    )


@tool(
    "request_send_email",
    "Create an approval preview to send an email from the user's connected mailbox. Nothing is sent until the user approves.",
    {
        "properties": {
            "to": {"type": "array", "items": {"type": "string"}},
            "cc": {"type": "array", "items": {"type": "string"}},
            "subject": {"type": "string"},
            "body": {"type": "string"},
            "attach_resume": {"type": "boolean"},
            "application_id": {"type": "string"},
        },
        "required": ["to", "subject", "body"],
    },
)
async def request_send_email(ctx: ToolContext, args: dict[str, Any]) -> Any:
    from app.email.service import get_connection, request_send
    from app.resumes.service import primary_resume

    conn = await get_connection(ctx.session, ctx.user.id, None)
    attachments: list[dict[str, Any]] = []
    if args.get("attach_resume"):
        resume = await primary_resume(ctx.session, ctx.user.id)
        if resume is not None:
            attachments.append({"type": "resume", "resume_id": str(resume.id)})
    to = [t for t in args.get("to", []) if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", str(t))]
    if not to:
        return {"error": "no valid recipient address"}
    approval = await request_send(
        ctx.session,
        ctx.user.id,
        connection=conn,
        to=to,
        cc=list(args.get("cc", [])),
        subject=args["subject"],
        body=args["body"],
        attachments=attachments,
        application_id=_uuid(args["application_id"]) if args.get("application_id") else None,
        preview_channel=ctx.channel,
        actor="agent",
    )
    ctx.approvals.append(approval)
    return {
        "approval_id": str(approval.id),
        "status": approval.status,
        "note": "preview shown to the user; they must approve before it is sent",
    }


@tool(
    "draft_linkedin_post",
    "Draft a LinkedIn post (not published).",
    {
        "properties": {
            "topic": {"type": "string"},
            "tone": {"type": "string", "enum": ["professional", "personal", "thoughtful"]},
            "length": {"type": "string", "enum": ["short", "medium", "long"]},
        },
        "required": ["topic"],
    },
)
async def draft_linkedin_post(ctx: ToolContext, args: dict[str, Any]) -> Any:
    from app.linkedin.service import draft_post

    return await draft_post(
        ctx.session, ctx.user.id, topic=args["topic"], tone=args.get("tone", "professional"), length=args.get("length", "medium")
    )


@tool(
    "draft_linkedin_message",
    "Draft a LinkedIn connection note or recruiter message (handed to the user to paste).",
    {
        "properties": {
            "kind": {"type": "string", "enum": ["connection_note", "recruiter_message", "inmail"]},
            "recipient_name": {"type": "string"},
            "recipient_role": {"type": "string"},
            "company": {"type": "string"},
            "context": {"type": "string"},
        },
        "required": ["kind", "context"],
    },
)
async def draft_linkedin_message(ctx: ToolContext, args: dict[str, Any]) -> Any:
    from app.linkedin.service import draft_message

    return await draft_message(
        ctx.session,
        ctx.user.id,
        kind=args["kind"],
        recipient_name=args.get("recipient_name"),
        recipient_role=args.get("recipient_role"),
        company=args.get("company"),
        context=args.get("context", ""),
    )


@tool(
    "request_linkedin_post",
    "Create an approval preview to publish a LinkedIn post. Nothing is published until approved.",
    {"properties": {"text": {"type": "string"}}, "required": ["text"]},
)
async def request_linkedin_post(ctx: ToolContext, args: dict[str, Any]) -> Any:
    from app.linkedin.service import request_publish

    approval = await request_publish(ctx.session, ctx.user.id, text=args["text"], preview_channel=ctx.channel, actor="agent")
    ctx.approvals.append(approval)
    return {"approval_id": str(approval.id), "status": approval.status}


# --- resume / prep / research ---------------------------------------------------


@tool(
    "tailor_resume",
    "Create a tailored version of the user's resume for a job, with an ATS keyword report.",
    {"properties": {"job_id": {"type": "string"}, "notes": {"type": "string"}}, "required": ["job_id"]},
)
async def tailor_resume(ctx: ToolContext, args: dict[str, Any]) -> Any:
    from app.resumes.service import primary_resume, tailor

    job = await ctx.session.get(m.Job, _uuid(args["job_id"]))
    if job is None:
        return {"error": "job not found"}
    resume = await primary_resume(ctx.session, ctx.user.id)
    if resume is None:
        return {"error": "no resume uploaded yet"}
    tailored, ats = await tailor(ctx.session, ctx.user.id, job=job, resume=resume, notes=args.get("notes"))
    return {"resume_id": str(tailored.id), "ats": ats, "excerpt": (tailored.text or "")[:600]}


INTERVIEW_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "company_overview": {"type": "string"},
        "likely_questions": {"type": "array", "items": {"type": "string"}},
        "questions_to_ask": {"type": "array", "items": {"type": "string"}},
        "tips": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["likely_questions", "questions_to_ask", "tips"],
}


async def build_interview_prep(session: AsyncSession, user_id: uuid.UUID, app: m.Application) -> dict[str, Any]:
    from app.ai.llm import get_llm
    from app.ai.usage import charge, ensure_within_limit
    from app.email.service import candidate_summary

    await ensure_within_limit(session, user_id)
    job = await session.get(m.Job, app.job_id) if app.job_id else None
    system = "You prepare a job seeker for an interview. Be specific to the role and company from the data given; do not invent facts about the company."
    prompt = f"ROLE: {app.title} at {app.company}\nCANDIDATE:\n" + untrusted(
        await candidate_summary(session, user_id), "candidate_profile"
    )
    if job is not None:
        prompt += "\nJOB POSTING:\n" + untrusted((job.description or "")[:5000], "job_posting")
    data = await get_llm().json(system=system, prompt=prompt, schema=INTERVIEW_SCHEMA, max_tokens=1200)
    await charge(session, user_id, "llm")
    return data


@tool(
    "interview_prep",
    "Build an interview prep pack for an application: likely questions, questions to ask, tips.",
    {"properties": {"application_id": {"type": "string"}}, "required": ["application_id"]},
)
async def interview_prep(ctx: ToolContext, args: dict[str, Any]) -> Any:
    from app.applications.service import get_owned

    app = await get_owned(ctx.session, ctx.user.id, _uuid(args["application_id"]))
    return await build_interview_prep(ctx.session, ctx.user.id, app)


_MAILTO = re.compile(r"mailto:([^\"'?\s>]+)", re.I)
_EMAIL = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")


@tool(
    "find_public_contacts",
    "Fetch a public web page the user points to (company careers/contact page) and extract publicly listed email contacts with the surrounding text as evidence. Never guesses addresses.",
    {"properties": {"company": {"type": "string"}, "page_url": {"type": "string"}}, "required": ["company", "page_url"]},
)
async def find_public_contacts(ctx: ToolContext, args: dict[str, Any]) -> Any:
    from app.jobs.sources.base import html_to_text

    url = str(args["page_url"])
    if not url.startswith(("http://", "https://")):
        return {"error": "page_url must be an http(s) URL"}
    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True, headers={"User-Agent": "LifeEasy/1.0"}) as client:
            resp = await client.get(url)
    except httpx.HTTPError as exc:
        return {"error": f"could not fetch page: {type(exc).__name__}"}
    if resp.is_error:
        return {"error": f"page returned HTTP {resp.status_code}"}
    html = resp.text[:500000]
    text = html_to_text(html)
    found: dict[str, str] = {}
    for match in list(_MAILTO.finditer(html)) + list(_EMAIL.finditer(text)):
        addr = match.group(1) if match.re is _MAILTO else match.group(0)
        addr = addr.strip().lower()
        if addr in found or addr.endswith((".png", ".jpg", ".gif")):
            continue
        pos = text.lower().find(addr)
        found[addr] = text[max(0, pos - 120) : pos + len(addr) + 120].replace("\n", " ") if pos >= 0 else ""
    if not found:
        return {"contacts": [], "note": "no public email addresses on that page"}
    contacts = []
    expires = datetime.now(UTC) + timedelta(days=90)
    for addr, excerpt in list(found.items())[:10]:
        row = m.RecruiterContact(
            user_id=ctx.user.id,
            company=str(args["company"])[:200],
            public_email=addr,
            source_url=url[:1000],
            source_excerpt=excerpt[:1000],
            expires_at=expires,
        )
        ctx.session.add(row)
        contacts.append({"email": addr, "source_url": url, "evidence": excerpt[:200]})
    await ctx.session.flush()
    return {"contacts": contacts, "retention": "kept 90 days, with source"}


@tool(
    "remember",
    "Store a durable fact or preference the user told you (e.g. 'prefers startups', 'notice period 30 days').",
    {
        "properties": {
            "content": {"type": "string"},
            "memory_type": {"type": "string", "enum": ["preference", "fact", "feedback"]},
        },
        "required": ["content"],
    },
)
async def remember_tool(ctx: ToolContext, args: dict[str, Any]) -> Any:
    from app.agent.memory import remember

    item = await remember(ctx.session, ctx.user.id, content=args["content"], memory_type=args.get("memory_type", "fact"))
    return {"ok": True, "memory_id": str(item.id)}
