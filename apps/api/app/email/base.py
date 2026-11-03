from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from email.message import EmailMessage
from email.utils import formatdate, make_msgid


@dataclass
class Attachment:
    filename: str
    content_type: str
    data: bytes


@dataclass
class InboundEmail:
    id: str
    from_addr: str
    subject: str
    received_at: datetime | None
    snippet: str = ""
    body: str = ""
    thread_id: str | None = None
    headers: dict[str, str] = field(default_factory=dict)


class EmailProvider:
    name = "base"
    account_email: str = ""

    async def send(
        self,
        *,
        to: list[str],
        cc: list[str],
        subject: str,
        body_text: str,
        attachments: list[Attachment],
        idempotency_key: str,
    ) -> dict[str, str]:
        raise NotImplementedError

    async def list_recent(self, *, since: datetime, max_results: int = 50) -> list[InboundEmail]:
        raise NotImplementedError

    async def get_message(self, message_id: str) -> InboundEmail:
        raise NotImplementedError


def build_mime(
    *,
    sender: str,
    to: list[str],
    cc: list[str],
    subject: str,
    body_text: str,
    attachments: list[Attachment],
    idempotency_key: str,
) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=False)
    msg["Message-ID"] = make_msgid(idempotency_key.replace(":", "-"), domain="life-easy.app")
    msg["X-LifeEasy-Idempotency"] = idempotency_key
    msg.set_content(body_text)
    for att in attachments:
        maintype, _, subtype = (att.content_type or "application/octet-stream").partition("/")
        msg.add_attachment(att.data, maintype=maintype, subtype=subtype or "octet-stream", filename=att.filename)
    return msg
