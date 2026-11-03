from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import current_user
from app.channels.linking import create_link_code, revoke_identity
from app.channels.pipeline import get_adapter
from app.channels.telegram import TelegramAdapter
from app.channels.whatsapp import WhatsAppAdapter
from app.config import get_settings
from app.db import models as m
from app.db.session import get_db
from app.security.ratelimit import rate_limit
from app.tasks.runner import enqueue

router = APIRouter(prefix="/api/v1", tags=["channels"])

# Webhook authentication never depends on the (swappable) delivery adapter.
_wa_verifier = WhatsAppAdapter()
_tg_verifier = TelegramAdapter()


async def _enqueue_all(channel: str, payload: dict[str, Any]) -> int:
    adapter = get_adapter(channel)
    messages = adapter.parse(payload)
    for msg in messages:
        await enqueue(
            "process_inbound_message",
            channel=channel,
            external_id=msg.external_id,
            text=msg.text,
            event_id=msg.event_id,
            display_name=msg.display_name,
            button_id=msg.button_id,
            reply_to=msg.reply_to,
        )
    return len(messages)


@router.get("/webhooks/whatsapp", include_in_schema=False)
async def whatsapp_verify(
    hub_mode: str | None = Query(default=None, alias="hub.mode"),
    hub_verify_token: str | None = Query(default=None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(default=None, alias="hub.challenge"),
) -> PlainTextResponse:
    import hmac

    token = get_settings().whatsapp_webhook_verify_token
    if not token:
        raise HTTPException(status_code=503, detail="WhatsApp webhook is not configured")
    if hub_mode == "subscribe" and hmac.compare_digest(hub_verify_token or "", token):
        return PlainTextResponse(hub_challenge or "", status_code=200)
    raise HTTPException(status_code=403, detail="Webhook verification failed")


@router.post("/webhooks/whatsapp", include_in_schema=False)
async def whatsapp_webhook(request: Request) -> dict[str, Any]:
    raw = await request.body()
    if not _wa_verifier.valid_signature(raw, request.headers.get("x-hub-signature-256")):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
    try:
        payload = await request.json()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc
    count = await _enqueue_all("whatsapp", payload if isinstance(payload, dict) else {})
    return {"status": "accepted", "message_events_received": count}


@router.post("/webhooks/telegram", include_in_schema=False)
async def telegram_webhook(
    request: Request, x_telegram_bot_api_secret_token: str | None = Header(default=None)
) -> dict[str, Any]:
    if not _tg_verifier.valid_secret(x_telegram_bot_api_secret_token):
        raise HTTPException(status_code=401, detail="Invalid webhook secret")
    try:
        payload = await request.json()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc
    count = await _enqueue_all("telegram", payload if isinstance(payload, dict) else {})
    return {"status": "accepted", "message_events_received": count}


@router.post("/channels/link-code", dependencies=[Depends(rate_limit("linkcode", 10))])
async def link_code(user: m.User = Depends(current_user), session: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    row = await create_link_code(session, user.id)
    return {
        "code": row.code,
        "expires_at": row.expires_at,
        "instructions": f"Send 'LINK {row.code}' to the Life Easy WhatsApp number or Telegram bot within 15 minutes.",
        "channels": {"whatsapp": get_adapter("whatsapp").configured(), "telegram": get_adapter("telegram").configured()},
    }


@router.get("/channels")
async def list_channels(user: m.User = Depends(current_user), session: AsyncSession = Depends(get_db)) -> list[dict[str, Any]]:
    rows = (
        await session.scalars(
            select(m.ChannelIdentity).where(m.ChannelIdentity.user_id == user.id, m.ChannelIdentity.revoked_at.is_(None))
        )
    ).all()
    return [
        {
            "id": r.id,
            "provider": r.provider,
            "display_name": r.display_name,
            "external_id_hint": f"...{r.external_id[-4:]}",
            "verified_at": r.verified_at,
        }
        for r in rows
    ]


@router.delete("/channels/{identity_id}", status_code=204)
async def unlink_channel(identity_id: uuid.UUID, user: m.User = Depends(current_user), session: AsyncSession = Depends(get_db)):  # noqa: ANN201
    await revoke_identity(session, user.id, identity_id)


@router.post("/channels/telegram/set-webhook")
async def telegram_set_webhook(_: m.User = Depends(current_user)) -> dict[str, Any]:
    """Registers this API's Telegram webhook URL with Telegram (run once after deploying)."""
    return await _tg_verifier.set_webhook(f"{get_settings().public_api_url}/api/v1/webhooks/telegram")
