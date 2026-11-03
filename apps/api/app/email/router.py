from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.approvals.schemas import ApprovalOut
from app.auth.deps import current_user
from app.config import get_settings
from app.core.audit import record_audit
from app.core.errors import AppError, NotFound
from app.core.logging import get_logger
from app.db import models as m
from app.db.session import get_db
from app.email import oauth, service
from app.email.schemas import ConnectionOut, DraftOut, DraftRequest, ImapConnectionCreate, InboxItem, SendRequest
from app.security.ratelimit import rate_limit

log = get_logger(__name__)
router = APIRouter(prefix="/api/v1", tags=["email"])

OAUTH_PROVIDERS = ("google", "microsoft", "linkedin")


@router.get("/email/connections", response_model=list[ConnectionOut])
async def list_connections(
    user: m.User = Depends(current_user), session: AsyncSession = Depends(get_db)
) -> list[m.OAuthConnection]:
    return await service.list_connections(session, user.id)


@router.post(
    "/email/connections/imap", response_model=ConnectionOut, status_code=201, dependencies=[Depends(rate_limit("imap", 10))]
)
async def add_imap(
    body: ImapConnectionCreate, user: m.User = Depends(current_user), session: AsyncSession = Depends(get_db)
) -> m.OAuthConnection:
    return await service.create_imap_connection(
        session,
        user.id,
        account_email=body.account_email,
        username=body.username,
        password=body.password,
        imap_host=body.imap_host,
        imap_port=body.imap_port,
        smtp_host=body.smtp_host,
        smtp_port=body.smtp_port,
    )


@router.delete("/email/connections/{connection_id}", status_code=204)
async def remove_connection(
    connection_id: uuid.UUID, user: m.User = Depends(current_user), session: AsyncSession = Depends(get_db)
):  # noqa: ANN201
    await service.disconnect(session, user.id, connection_id)


@router.get("/connections/oauth/{provider}/start")
async def oauth_start(provider: str, user: m.User = Depends(current_user)) -> dict[str, str]:
    if provider not in OAUTH_PROVIDERS:
        raise NotFound("unknown provider")
    return {"url": oauth.authorize_url(user.id, provider)}


@router.get("/connections/oauth/{provider}/callback", include_in_schema=False)
async def oauth_callback(
    provider: str,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    session: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    frontend = get_settings().frontend_origin.rstrip("/")
    if provider not in OAUTH_PROVIDERS or error or not code or not state:
        return RedirectResponse(f"{frontend}/app/settings?error={error or 'oauth_cancelled'}", status_code=302)
    try:
        user_id, state_provider = oauth.read_state(state)
        if state_provider != provider:
            raise AppError("state/provider mismatch")
        exchanged = await oauth.exchange_code(provider, code)
        conn = await oauth.store_connection(session, user_id, provider, exchanged)
        await record_audit(
            session,
            user_id=user_id,
            actor="user",
            event_type="connection.create",
            target_type="connection",
            target_id=conn.id,
            details={"provider": provider},
        )
    except AppError as exc:
        log.warning("oauth callback failed", provider=provider, error=exc.message)
        return RedirectResponse(f"{frontend}/app/settings?error={exc.code}", status_code=302)
    return RedirectResponse(f"{frontend}/app/settings?connected={provider}", status_code=302)


@router.post("/email/drafts", response_model=DraftOut, dependencies=[Depends(rate_limit("draft", 30))])
async def draft(body: DraftRequest, user: m.User = Depends(current_user), session: AsyncSession = Depends(get_db)) -> DraftOut:
    application = None
    job = None
    if body.application_id:
        application = await session.get(m.Application, body.application_id)
        if application is None or application.user_id != user.id:
            raise NotFound("application not found")
        if application.job_id:
            job = await session.get(m.Job, application.job_id)
    if body.job_id:
        job = await session.get(m.Job, body.job_id)
        if job is None:
            raise NotFound("job not found")
    data = await service.draft_email(
        session,
        user.id,
        purpose=body.purpose,
        to_name=body.to_name,
        context=body.context,
        tone=body.tone,
        application=application,
        job=job,
    )
    return DraftOut(**data)


@router.post("/email/send", response_model=ApprovalOut, status_code=201)
async def send(
    body: SendRequest, user: m.User = Depends(current_user), session: AsyncSession = Depends(get_db)
) -> m.ActionApproval:
    """Never sends directly: creates an approval whose preview must be confirmed first."""
    conn = await service.get_connection(session, user.id, body.connection_id)
    return await service.request_send(
        session,
        user.id,
        connection=conn,
        to=list(body.to),
        cc=list(body.cc),
        subject=body.subject,
        body=body.body,
        attachments=[a.model_dump(mode="json") for a in body.attachments],
        application_id=body.application_id,
        preview_channel="web",
    )


@router.get("/email/inbox", response_model=list[InboxItem], dependencies=[Depends(rate_limit("inbox", 20))])
async def inbox(
    connection_id: uuid.UUID | None = None,
    since_hours: int = Query(default=48, ge=1, le=24 * 14),
    user: m.User = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> list[InboxItem]:
    conn = await service.get_connection(session, user.id, connection_id)
    provider = await service.provider_for(session, conn)
    items = await provider.list_recent(since=datetime.now(UTC) - timedelta(hours=since_hours), max_results=50)
    return [
        InboxItem(id=i.id, from_addr=i.from_addr, subject=i.subject, received_at=i.received_at, snippet=i.snippet[:300])
        for i in items
    ]
