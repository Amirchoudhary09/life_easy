"""WhatsApp Business Platform (Cloud API). One Life Easy business number; users message it from their own phone."""

from __future__ import annotations

import hashlib
import hmac
from typing import Any

import httpx

from app.channels.base import Button, ChannelAdapter, InboundMessage, chunk_text
from app.config import get_settings
from app.core.errors import ProviderError, ProviderNotConfigured


class WhatsAppAdapter(ChannelAdapter):
    name = "whatsapp"

    def configured(self) -> bool:
        s = get_settings()
        return bool(s.whatsapp_access_token and s.whatsapp_phone_number_id and s.whatsapp_app_secret)

    def valid_signature(self, raw_body: bytes, signature_header: str | None) -> bool:
        secret = get_settings().whatsapp_app_secret
        if not secret or not signature_header or not signature_header.startswith("sha256="):
            return False
        digest = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(f"sha256={digest}", signature_header)

    def parse(self, payload: dict[str, Any]) -> list[InboundMessage]:
        out: list[InboundMessage] = []
        for entry in payload.get("entry", []) or []:
            for change in entry.get("changes", []) or []:
                if change.get("field") != "messages":
                    continue
                value = change.get("value", {}) or {}
                names = {c.get("wa_id"): (c.get("profile") or {}).get("name") for c in value.get("contacts", []) or []}
                for msg in value.get("messages", []) or []:
                    sender = str(msg.get("from", ""))
                    mid = str(msg.get("id", ""))
                    if not sender or not mid:
                        continue
                    kind = msg.get("type")
                    text, button_id = "", None
                    if kind == "text":
                        text = str((msg.get("text") or {}).get("body", ""))
                    elif kind == "interactive":
                        inter = msg.get("interactive") or {}
                        reply = inter.get("button_reply") or inter.get("list_reply") or {}
                        button_id = reply.get("id")
                        text = str(reply.get("title", ""))
                    elif kind == "button":  # template quick-reply
                        button_id = (msg.get("button") or {}).get("payload")
                        text = str((msg.get("button") or {}).get("text", ""))
                    else:
                        text = f"[{kind} message]"
                    out.append(
                        InboundMessage(
                            provider=self.name,
                            external_id=sender,
                            text=text,
                            event_id=mid,
                            display_name=names.get(sender),
                            button_id=button_id,
                        )
                    )
        return out

    def _url(self) -> str:
        s = get_settings()
        return f"https://graph.facebook.com/{s.whatsapp_graph_api_version}/{s.whatsapp_phone_number_id}/messages"

    async def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.configured():
            raise ProviderNotConfigured("WhatsApp Cloud API is not configured")
        headers = {"Authorization": f"Bearer {get_settings().whatsapp_access_token}"}
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                self._url(), headers=headers, json={"messaging_product": "whatsapp", "recipient_type": "individual", **payload}
            )
        if resp.is_error:
            raise ProviderError(f"WhatsApp send failed with HTTP {resp.status_code}")
        return resp.json()

    async def send_text(self, external_id: str, text: str) -> None:
        for chunk in chunk_text(text):
            await self._post({"to": external_id, "type": "text", "text": {"preview_url": False, "body": chunk}})

    async def send_buttons(self, external_id: str, text: str, buttons: list[Button]) -> None:
        chunks = chunk_text(text, 1000)
        for chunk in chunks[:-1]:
            await self._post({"to": external_id, "type": "text", "text": {"preview_url": False, "body": chunk}})
        body = chunks[-1] if chunks else "Choose an option"
        await self._post(
            {
                "to": external_id,
                "type": "interactive",
                "interactive": {
                    "type": "button",
                    "body": {"text": body},
                    "action": {
                        "buttons": [{"type": "reply", "reply": {"id": b.id[:256], "title": b.label[:20]}} for b in buttons[:3]]
                    },
                },
            }
        )
