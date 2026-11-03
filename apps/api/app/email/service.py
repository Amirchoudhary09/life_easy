"""Email connections, AI drafts, and the send executor (runs only after approval)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.llm import get_llm, untrusted
from app.ai.usage import charge, ensure_within_limit
from app.approvals.service import create_approval, register_executor
from app.core.audit import record_audit
from app.core.errors import NotFound, ProviderError, ProviderNotConfigured
from app.db import models as m
from app.email.base import Attachment, EmailProvider
from app.email.gmail import GmailProvider
from app.email.graph import GraphProvider
from app.email.imap_smtp import ImapSmtpProvider
from app.email.oauth import ensure_access_token
from app.resumes.storage import get_storage
from app.security.crypto import get_secret_box


async def list_connections(
    session: AsyncSession, user_id: uuid.UUID, *, providers: tuple[str, ...] | None = None
) -> list[m.OAuthConnection]:
    stmt = select(m.OAuthConnection).where(m.OAuthConnection.user_id == user_id, m.OAuthConnection.revoked_at.is_(None))
    if providers:
        stmt = stmt.where(m.OAuthConnection.provider.in_(providers))
    return list((await session.scalars(stmt.order_by(m.OAuthConnection.created_at))).all())


EMAIL_PROVIDERS = ("google", "microsoft", "imap")


async def get_connection(session: AsyncSession, user_id: uuid.UUID, connection_id: uuid.UUID | None) -> m.OAuthConnection:
    if connection_id is not None:
        conn = await session.get(m.OAuthConnection, connection_id)
        if conn is None or conn.user_id != user_id or conn.revoked_at is not None:
            raise NotFound("email connection not found")
        if conn.provider not in EMAIL_PROVIDERS:
            raise NotFound("that connection is not an email account")
        return conn
    conns = await list_connections(session, user_id, providers=EMAIL_PROVIDERS)
    if not conns:
        raise ProviderNotConfigured("connect an email account first (Settings > Email)")
    return conns[0]


async def provider_for(session: AsyncSession, conn: m.OAuthConnection) -> EmailProvider:
    if conn.provider == "google":
        return GmailProvider(await ensure_access_token(session, conn), conn.account_email)
    if conn.provider == "microsoft":
        return GraphProvider(await ensure_access_token(session, conn), conn.account_email)
    if conn.provider == "imap":
        extra = conn.extra or {}
        if not conn.access_token_enc:
            raise ProviderError("IMAP connection has no stored password")
        return ImapSmtpProvider(
            account_email=conn.account_email,
            username=str(extra.get("username") or conn.account_email),
            password=get_secret_box().decrypt(conn.access_token_enc),
            imap_host=str(extra["imap_host"]),
            imap_port=int(extra.get("imap_port", 993)),
            smtp_host=str(extra["smtp_host"]),
            smtp_port=int(extra.get("smtp_port", 587)),
        )
    raise ProviderError(f"unsupported email provider {conn.provider}")


async def create_imap_connection(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    account_email: str,
    username: str | None,
    password: str,
    imap_host: str,
    imap_port: int,
    smtp_host: str,
    smtp_port: int,
) -> m.OAuthConnection:
    probe = ImapSmtpProvider(
        account_email=account_email,
        username=username or account_email,
        password=password,
        imap_host=imap_host,
        imap_port=imap_port,
        smtp_host=smtp_host,
        smtp_port=smtp_port,
    )
    await probe.verify_login()
    conn = await session.scalar(
        select(m.OAuthConnection).where(
            m.OAuthConnection.user_id == user_id,
            m.OAuthConnection.provider == "imap",
            m.OAuthConnection.account_email == account_email.lower(),
        )
    )
    if conn is None:
        conn = m.OAuthConnection(user_id=user_id, provider="imap", account_email=account_email.lower())
        session.add(conn)
    conn.access_token_enc = get_secret_box().encrypt(password)
    conn.refresh_token_enc = None
    conn.token_expires_at = None
    conn.scopes = ["imap", "smtp"]
    conn.extra = {
        "username": username or account_email,
        "imap_host": imap_host,
        "imap_port": imap_port,
        "smtp_host": smtp_host,
        "smtp_port": smtp_port,
    }
    conn.revoked_at = None
    conn.last_error = None
    await session.flush()
    await record_audit(
        session,
        user_id=user_id,
        actor="user",
        event_type="connection.create",
        target_type="connection",
        target_id=conn.id,
        details={"provider": "imap"},
    )
    return conn


async def disconnect(session: AsyncSession, user_id: uuid.UUID, connection_id: uuid.UUID) -> None:
    from datetime import UTC, datetime

    conn = await session.get(m.OAuthConnection, connection_id)
    if conn is None or conn.user_id != user_id:
        raise NotFound("connection not found")
    conn.revoked_at = datetime.now(UTC)
    conn.access_token_enc = None
    conn.refresh_token_enc = None
    await record_audit(
        session,
        user_id=user_id,
        actor="user",
        event_type="connection.revoke",
        target_type="connection",
        target_id=conn.id,
        details={"provider": conn.provider},
    )


DRAFT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"subject": {"type": "string"}, "body": {"type": "string"}},
    "required": ["subject", "body"],
}

PURPOSE_HINTS = {
    "application": "a job application email that introduces the candidate and asks to be considered",
    "follow_up": "a short, polite follow-up on an application sent earlier",
    "recruiter_outreach": "a first message to a recruiter about a specific role or team",
    "thank_you": "a thank-you note after an interview",
    "custom": "an email as described in the context",
}


async def candidate_summary(session: AsyncSession, user_id: uuid.UUID) -> str:
    user = await session.get(m.User, user_id)
    profile = await session.get(m.Profile, user_id)
    parts = [f"Name: {user.display_name or ''}" if user else ""]
    if profile:
        parts += [
            f"Headline: {profile.headline or ''}",
            f"Location: {profile.location or ''}",
            f"Skills: {', '.join((profile.skills or [])[:25])}",
            f"Summary: {profile.summary or ''}",
        ]
    return "\n".join(p for p in parts if p and not p.endswith(": "))


async def draft_email(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    purpose: str,
    to_name: str | None,
    context: str,
    tone: str,
    application: m.Application | None = None,
    job: m.Job | None = None,
) -> dict[str, str]:
    await ensure_within_limit(session, user_id)
    llm = get_llm()
    system = (
        "You write career emails for a job seeker. Write in the first person as the candidate, in a "
        f"{tone} tone, under 180 words, no placeholders like [Name] unless the detail is unknown, no exaggeration, "
        "and nothing the candidate profile does not support. Return a subject and a plain-text body."
    )
    prompt = f"PURPOSE: {PURPOSE_HINTS.get(purpose, purpose)}\n"
    if to_name:
        prompt += f"RECIPIENT NAME: {to_name}\n"
    prompt += "\nCANDIDATE:\n" + untrusted(await candidate_summary(session, user_id), "candidate_profile") + "\n"
    if application is not None:
        prompt += f"\nAPPLICATION: {application.title} at {application.company}, status {application.status}, applied {application.applied_at.date() if application.applied_at else 'not yet'}\n"
    if job is not None:
        prompt += f"\nJOB: {job.title} at {job.company}\n" + untrusted((job.description or "")[:4000], "job_posting") + "\n"
    if context:
        prompt += "\nCONTEXT FROM THE CANDIDATE:\n" + untrusted(context, "user_notes") + "\n"
    data = await llm.json(system=system, prompt=prompt, schema=DRAFT_SCHEMA, max_tokens=800)
    await charge(session, user_id, "llm")
    return {"subject": str(data.get("subject") or "").strip()[:500], "body": str(data.get("body") or "").strip()}


async def request_send(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    connection: m.OAuthConnection,
    to: list[str],
    cc: list[str],
    subject: str,
    body: str,
    attachments: list[dict[str, Any]],
    application_id: uuid.UUID | None,
    preview_channel: str | None,
    actor: str = "user",
) -> m.ActionApproval:
    refs: list[dict[str, Any]] = []
    for att in attachments:
        resume = await session.get(m.Resume, uuid.UUID(str(att["resume_id"])))
        if resume is None or resume.user_id != user_id:
            raise NotFound("attachment resume not found")
        refs.append({"type": "resume", "resume_id": str(resume.id), "filename": resume.filename})
    if application_id is not None:
        app = await session.get(m.Application, application_id)
        if app is None or app.user_id != user_id:
            raise NotFound("application not found")
    return await create_approval(
        session,
        user_id,
        action_type="send_email",
        channel=f"email:{connection.account_email}",
        destination={"from": connection.account_email, "to": [t.lower() for t in to], "cc": [c.lower() for c in cc]},
        subject=subject,
        body=body,
        attachments=refs,
        payload={"connection_id": str(connection.id)},
        preview_channel=preview_channel,
        related_application_id=application_id,
        actor=actor,
    )


@register_executor("send_email")
async def _execute_send(session: AsyncSession, approval: m.ActionApproval) -> dict[str, Any]:
    conn = await session.get(m.OAuthConnection, uuid.UUID(str(approval.payload["connection_id"])))
    if conn is None or conn.user_id != approval.user_id or conn.revoked_at is not None:
        raise ProviderError("the email connection used for this preview is no longer available")
    provider = await provider_for(session, conn)
    storage = get_storage()
    files: list[Attachment] = []
    for ref in approval.attachments:
        resume = await session.get(m.Resume, uuid.UUID(str(ref["resume_id"])))
        if resume is None or resume.user_id != approval.user_id:
            raise ProviderError("attachment no longer exists")
        files.append(
            Attachment(filename=resume.filename, content_type=resume.content_type, data=await storage.get(resume.object_key))
        )
    dest = approval.destination
    result = await provider.send(
        to=list(dest.get("to", [])),
        cc=list(dest.get("cc", [])),
        subject=approval.subject or "",
        body_text=approval.body,
        attachments=files,
        idempotency_key=approval.idempotency_key,
    )
    return {"provider": conn.provider, "from": conn.account_email, **result}
