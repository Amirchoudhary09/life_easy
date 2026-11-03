"""Gmail REST API provider (OAuth scopes: gmail.send, gmail.readonly)."""

from __future__ import annotations

import base64
from datetime import datetime
from email import message_from_bytes
from email.utils import parsedate_to_datetime

import httpx

from app.core.errors import ProviderError
from app.email.base import EmailProvider, InboundEmail, build_mime

BASE = "https://gmail.googleapis.com/gmail/v1/users/me"


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None


class GmailProvider(EmailProvider):
    name = "google"

    def __init__(self, access_token: str, account_email: str) -> None:
        self._token = access_token
        self.account_email = account_email

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=30.0, headers={"Authorization": f"Bearer {self._token}"})

    async def send(self, *, to, cc, subject, body_text, attachments, idempotency_key):  # type: ignore[no-untyped-def]
        msg = build_mime(
            sender=self.account_email,
            to=to,
            cc=cc,
            subject=subject,
            body_text=body_text,
            attachments=attachments,
            idempotency_key=idempotency_key,
        )
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")
        async with self._client() as client:
            resp = await client.post(f"{BASE}/messages/send", json={"raw": raw})
        if resp.is_error:
            raise ProviderError(f"Gmail send failed with HTTP {resp.status_code}")
        data = resp.json()
        return {
            "provider_message_id": str(data.get("id", "")),
            "thread_id": str(data.get("threadId", "")),
            "message_id": msg["Message-ID"],
        }

    async def list_recent(self, *, since: datetime, max_results: int = 50) -> list[InboundEmail]:
        query = f"after:{int(since.timestamp())} -category:promotions -category:social"
        async with self._client() as client:
            resp = await client.get(f"{BASE}/messages", params={"q": query, "maxResults": max_results})
            if resp.is_error:
                raise ProviderError(f"Gmail list failed with HTTP {resp.status_code}")
            ids = [item["id"] for item in resp.json().get("messages", [])]
            out: list[InboundEmail] = []
            for mid in ids:
                meta = await client.get(
                    f"{BASE}/messages/{mid}",
                    params={"format": "metadata", "metadataHeaders": ["From", "Subject", "Date"]},
                )
                if meta.is_error:
                    continue
                data = meta.json()
                headers = {h["name"].lower(): h["value"] for h in (data.get("payload") or {}).get("headers", [])}
                out.append(
                    InboundEmail(
                        id=mid,
                        from_addr=headers.get("from", ""),
                        subject=headers.get("subject", ""),
                        received_at=_parse_date(headers.get("date")),
                        snippet=data.get("snippet", ""),
                        thread_id=data.get("threadId"),
                        headers=headers,
                    )
                )
        return out

    async def get_message(self, message_id: str) -> InboundEmail:
        async with self._client() as client:
            resp = await client.get(f"{BASE}/messages/{message_id}", params={"format": "raw"})
        if resp.is_error:
            raise ProviderError(f"Gmail get failed with HTTP {resp.status_code}")
        data = resp.json()
        raw = base64.urlsafe_b64decode(data.get("raw", "") + "==")
        msg = message_from_bytes(raw)
        body = ""
        parts = msg.walk() if msg.is_multipart() else [msg]
        for part in parts:
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    body += payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        return InboundEmail(
            id=message_id,
            from_addr=msg.get("From", ""),
            subject=msg.get("Subject", ""),
            received_at=_parse_date(msg.get("Date")),
            snippet=data.get("snippet", ""),
            body=body[:20000],
            thread_id=data.get("threadId"),
        )
