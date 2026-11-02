from __future__ import annotations

import hashlib
import hmac
import os
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

router = APIRouter(prefix="/api/v1/webhooks/whatsapp", tags=["WhatsApp"])

VERIFY_TOKEN = os.getenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN", "")
APP_SECRET = os.getenv("WHATSAPP_APP_SECRET", "")
ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
GRAPH_API_VERSION = os.getenv("WHATSAPP_GRAPH_API_VERSION", "")


@router.get("")
async def verify_webhook(
    hub_mode: str | None = Query(default=None, alias="hub.mode"),
    hub_verify_token: str | None = Query(default=None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(default=None, alias="hub.challenge"),
) -> PlainTextResponse:
    """Meta webhook subscription handshake."""
    if not VERIFY_TOKEN:
        raise HTTPException(status_code=503, detail="WhatsApp webhook is not configured")
    if hub_mode == "subscribe" and hmac.compare_digest(hub_verify_token or "", VERIFY_TOKEN):
        return PlainTextResponse(hub_challenge or "", status_code=200)
    raise HTTPException(status_code=403, detail="Webhook verification failed")


def _valid_signature(raw_body: bytes, signature_header: str | None) -> bool:
    if not APP_SECRET or not signature_header or not signature_header.startswith("sha256="):
        return False
    digest = hmac.new(APP_SECRET.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    expected = f"sha256={digest}"
    return hmac.compare_digest(expected, signature_header)


def _extract_messages(payload: dict[str, Any]) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            if change.get("field") == "messages":
                messages.extend(value.get("messages", []) or [])
    return messages


@router.post("")
async def receive_webhook(request: Request) -> dict[str, Any]:
    """Validate Meta's signature and acknowledge the event.

    Message-to-user routing and AI orchestration are intentionally not enabled
    until the multi-tenant identity store and queue worker are implemented.
    """
    raw_body = await request.body()
    if not _valid_signature(raw_body, request.headers.get("x-hub-signature-256")):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc

    messages = _extract_messages(payload if isinstance(payload, dict) else {})
    # Do not log or persist phone numbers/message bodies here. A verified
    # webhook is acknowledged; the user-isolated processing pipeline is next.
    return {"status": "accepted", "message_events_received": len(messages)}


async def send_text_message(recipient: str, text: str) -> dict[str, Any]:
    """Send a WhatsApp text reply using the configured Cloud API credentials."""
    if not all((ACCESS_TOKEN, PHONE_NUMBER_ID, GRAPH_API_VERSION)):
        raise RuntimeError("WhatsApp Cloud API credentials are not configured")
    if not recipient or not text.strip():
        raise ValueError("recipient and message text are required")

    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": recipient,
        "type": "text",
        "text": {"preview_url": False, "body": text},
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(url, headers=headers, json=payload)
    if response.is_error:
        # Avoid exposing bearer tokens; Meta's response body is returned only
        # to the server-side caller and should not be written to public logs.
        raise RuntimeError(f"WhatsApp send failed with HTTP {response.status_code}")
    return response.json()
