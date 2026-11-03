"""Microsoft Graph provider for Outlook / Microsoft 365 (scopes: Mail.Send, Mail.Read, User.Read, offline_access)."""

from __future__ import annotations

import base64
from datetime import datetime

import httpx

from app.core.errors import ProviderError
from app.email.base import EmailProvider, InboundEmail
from app.jobs.sources.base import html_to_text, parse_dt

BASE = "https://graph.microsoft.com/v1.0"


def _from(item: dict) -> str:
    sender = (item.get("from") or {}).get("emailAddress") or {}
    return f"{sender.get('name', '')} <{sender.get('address', '')}>".strip()


class GraphProvider(EmailProvider):
    name = "microsoft"

    def __init__(self, access_token: str, account_email: str) -> None:
        self._token = access_token
        self.account_email = account_email

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=30.0, headers={"Authorization": f"Bearer {self._token}"})

    async def send(self, *, to, cc, subject, body_text, attachments, idempotency_key):  # type: ignore[no-untyped-def]
        message = {
            "subject": subject,
            "body": {"contentType": "Text", "content": body_text},
            "toRecipients": [{"emailAddress": {"address": a}} for a in to],
            "ccRecipients": [{"emailAddress": {"address": a}} for a in cc],
            "internetMessageHeaders": [{"name": "X-LifeEasy-Idempotency", "value": idempotency_key}],
            "attachments": [
                {
                    "@odata.type": "#microsoft.graph.fileAttachment",
                    "name": a.filename,
                    "contentType": a.content_type,
                    "contentBytes": base64.b64encode(a.data).decode("ascii"),
                }
                for a in attachments
            ],
        }
        async with self._client() as client:
            resp = await client.post(
                f"{BASE}/me/sendMail",
                json={"message": message, "saveToSentItems": True},
                headers={"client-request-id": idempotency_key[:40]},
            )
        if resp.is_error:
            raise ProviderError(f"Outlook send failed with HTTP {resp.status_code}")
        return {"provider_message_id": resp.headers.get("request-id", ""), "message_id": idempotency_key}

    async def list_recent(self, *, since: datetime, max_results: int = 50) -> list[InboundEmail]:
        params = {
            "$filter": f"receivedDateTime ge {since.strftime('%Y-%m-%dT%H:%M:%SZ')}",
            "$top": str(max_results),
            "$select": "id,subject,from,receivedDateTime,bodyPreview,conversationId",
            "$orderby": "receivedDateTime desc",
        }
        async with self._client() as client:
            resp = await client.get(f"{BASE}/me/mailFolders/inbox/messages", params=params)
        if resp.is_error:
            raise ProviderError(f"Outlook list failed with HTTP {resp.status_code}")
        return [
            InboundEmail(
                id=item["id"],
                from_addr=_from(item),
                subject=item.get("subject", ""),
                received_at=parse_dt(item.get("receivedDateTime")),
                snippet=item.get("bodyPreview", ""),
                thread_id=item.get("conversationId"),
            )
            for item in resp.json().get("value", [])
        ]

    async def get_message(self, message_id: str) -> InboundEmail:
        async with self._client() as client:
            resp = await client.get(
                f"{BASE}/me/messages/{message_id}",
                params={"$select": "id,subject,from,receivedDateTime,body,bodyPreview,conversationId"},
            )
        if resp.is_error:
            raise ProviderError(f"Outlook get failed with HTTP {resp.status_code}")
        item = resp.json()
        body = item.get("body") or {}
        text = body.get("content", "")
        if (body.get("contentType") or "").lower() == "html":
            text = html_to_text(text)
        return InboundEmail(
            id=item["id"],
            from_addr=_from(item),
            subject=item.get("subject", ""),
            received_at=parse_dt(item.get("receivedDateTime")),
            snippet=item.get("bodyPreview", ""),
            body=text[:20000],
            thread_id=item.get("conversationId"),
        )
