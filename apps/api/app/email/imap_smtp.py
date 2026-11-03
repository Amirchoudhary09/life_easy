"""Generic IMAP/SMTP provider (app passwords): Yahoo, Zoho, iCloud, custom domains, or Gmail/Outlook without OAuth."""

from __future__ import annotations

import asyncio
import email
import imaplib
from datetime import datetime
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime

import aiosmtplib

from app.core.errors import ProviderError
from app.email.base import EmailProvider, InboundEmail, build_mime


def _decode(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:  # noqa: BLE001
        return value


def _date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None


class ImapSmtpProvider(EmailProvider):
    name = "imap"

    def __init__(
        self,
        *,
        account_email: str,
        username: str,
        password: str,
        imap_host: str,
        imap_port: int,
        smtp_host: str,
        smtp_port: int,
        smtp_tls: bool = True,
    ) -> None:
        self.account_email = account_email
        self._username = username
        self._password = password
        self._imap_host, self._imap_port = imap_host, imap_port
        self._smtp_host, self._smtp_port, self._smtp_tls = smtp_host, smtp_port, smtp_tls

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
        try:
            await aiosmtplib.send(
                msg,
                hostname=self._smtp_host,
                port=self._smtp_port,
                username=self._username,
                password=self._password,
                start_tls=self._smtp_tls and self._smtp_port != 465,
                use_tls=self._smtp_port == 465,
                timeout=30,
            )
        except aiosmtplib.SMTPException as exc:
            raise ProviderError(f"SMTP send failed: {type(exc).__name__}") from exc
        return {"message_id": msg["Message-ID"]}

    def _imap(self) -> imaplib.IMAP4_SSL:
        try:
            conn = imaplib.IMAP4_SSL(self._imap_host, self._imap_port, timeout=30)
            conn.login(self._username, self._password)
            return conn
        except (imaplib.IMAP4.error, OSError) as exc:
            raise ProviderError(f"IMAP login failed: {type(exc).__name__}") from exc

    async def verify_login(self) -> None:
        def _check() -> None:
            conn = self._imap()
            conn.logout()

        await asyncio.to_thread(_check)

    async def list_recent(self, *, since: datetime, max_results: int = 50) -> list[InboundEmail]:
        def _list() -> list[InboundEmail]:
            conn = self._imap()
            try:
                conn.select("INBOX", readonly=True)
                _, data = conn.search(None, "SINCE", since.strftime("%d-%b-%Y"))
                ids = data[0].split()[-max_results:]
                out: list[InboundEmail] = []
                for mid in reversed(ids):
                    _, parts = conn.fetch(mid, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
                    raw = b"".join(p[1] for p in parts if isinstance(p, tuple))
                    msg = email.message_from_bytes(raw)
                    out.append(
                        InboundEmail(
                            id=mid.decode(),
                            from_addr=_decode(msg.get("From")),
                            subject=_decode(msg.get("Subject")),
                            received_at=_date(msg.get("Date")),
                        )
                    )
                return out
            finally:
                conn.logout()

        return await asyncio.to_thread(_list)

    async def get_message(self, message_id: str) -> InboundEmail:
        def _get() -> InboundEmail:
            conn = self._imap()
            try:
                conn.select("INBOX", readonly=True)
                _, parts = conn.fetch(message_id.encode(), "(RFC822)")
                raw = b"".join(p[1] for p in parts if isinstance(p, tuple))
                msg = email.message_from_bytes(raw)
                body = ""
                for part in msg.walk() if msg.is_multipart() else [msg]:
                    if part.get_content_type() == "text/plain":
                        payload = part.get_payload(decode=True)
                        if payload:
                            body += payload.decode(part.get_content_charset() or "utf-8", errors="replace")
                return InboundEmail(
                    id=message_id,
                    from_addr=_decode(msg.get("From")),
                    subject=_decode(msg.get("Subject")),
                    received_at=_date(msg.get("Date")),
                    body=body[:20000],
                )
            finally:
                conn.logout()

        return await asyncio.to_thread(_get)
