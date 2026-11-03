"""Follow-up automation: when an application goes quiet, draft the follow-up and ask for approval."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from app.applications.service import ACTIVE_STATUSES
from app.approvals.service import preview_text
from app.automations.notify import notify_user
from app.channels.pipeline import approval_buttons
from app.core.errors import AppError
from app.core.logging import get_logger
from app.db import models as m
from app.db.session import get_session_factory
from app.email.service import draft_email, get_connection, request_send

log = get_logger(__name__)
REMIND_AGAIN_DAYS = 3


async def run_follow_ups() -> dict[str, Any]:
    drafted = reminded = 0
    async with get_session_factory()() as session:
        now = datetime.now(UTC)
        apps = (
            await session.scalars(
                select(m.Application).where(m.Application.status.in_(ACTIVE_STATUSES), m.Application.next_follow_up_at <= now)
            )
        ).all()
        for app in apps:
            open_fu = await session.scalar(
                select(m.FollowUp).where(m.FollowUp.application_id == app.id, m.FollowUp.status == "drafted")
            )
            if open_fu is not None:
                continue
            contact = await session.get(m.RecruiterContact, app.contact_id) if app.contact_id else None
            try:
                if contact is not None and contact.public_email:
                    conn = await get_connection(session, app.user_id, None)
                    draft = await draft_email(
                        session,
                        app.user_id,
                        purpose="follow_up",
                        to_name=contact.name,
                        context=f"Following up on my application for {app.title}.",
                        tone="professional",
                        application=app,
                    )
                    approval = await request_send(
                        session,
                        app.user_id,
                        connection=conn,
                        to=[contact.public_email],
                        cc=[],
                        subject=draft["subject"],
                        body=draft["body"],
                        attachments=[],
                        application_id=app.id,
                        preview_channel="automation",
                        actor="agent",
                    )
                    session.add(
                        m.FollowUp(
                            user_id=app.user_id, application_id=app.id, due_at=now, status="drafted", approval_id=approval.id
                        )
                    )
                    app.next_follow_up_at = now + timedelta(days=7)
                    await session.flush()
                    await notify_user(
                        session,
                        app.user_id,
                        "Follow-up due for your application:\n\n" + preview_text(approval),
                        buttons=approval_buttons(approval),
                        kind="follow_up",
                    )
                    drafted += 1
                else:
                    await notify_user(
                        session,
                        app.user_id,
                        f"Follow-up due: {app.title} at {app.company} (applied {app.applied_at.date() if app.applied_at else 'earlier'}). I don't have a recruiter email for it. Tell me the address and I'll draft the follow-up, or say 'skip follow-up for {app.company}'.",
                        kind="follow_up_reminder",
                    )
                    app.next_follow_up_at = now + timedelta(days=REMIND_AGAIN_DAYS)
                    reminded += 1
            except AppError as exc:
                log.warning("follow-up skipped", application_id=str(app.id), error=exc.message)
                app.next_follow_up_at = now + timedelta(days=REMIND_AGAIN_DAYS)
        await session.commit()
    return {"drafted": drafted, "reminded": reminded}
