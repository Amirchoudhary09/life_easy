from __future__ import annotations

from datetime import datetime
from typing import Any

from app.ai.llm import FakeLLM, set_llm
from app.db import models as m
from app.email import service as email_service
from app.email.base import Attachment, EmailProvider, InboundEmail, build_mime
from app.email.imap_smtp import ImapSmtpProvider
from app.security.crypto import get_secret_box
from sqlalchemy import select


class FakeProvider(EmailProvider):
    name = "fake"

    def __init__(self, account_email: str = "me@mail.example.com", inbox: list[InboundEmail] | None = None) -> None:
        self.account_email = account_email
        self.sent: list[dict[str, Any]] = []
        self.inbox = inbox or []

    async def send(self, *, to, cc, subject, body_text, attachments, idempotency_key):  # type: ignore[no-untyped-def]
        self.sent.append(
            {"to": to, "cc": cc, "subject": subject, "body": body_text, "attachments": attachments, "key": idempotency_key}
        )
        return {"message_id": f"<{idempotency_key}@test>"}

    async def list_recent(self, *, since: datetime, max_results: int = 50) -> list[InboundEmail]:
        return list(self.inbox)


async def _imap(client, auth, monkeypatch) -> dict:  # noqa: ANN001
    async def ok(self):  # noqa: ANN001
        return None

    monkeypatch.setattr(ImapSmtpProvider, "verify_login", ok)
    resp = await client.post(
        "/api/v1/email/connections/imap",
        headers=auth,
        json={
            "account_email": "Me@Mail.example.com",
            "password": "app-password-123",
            "imap_host": "imap.mail.test",
            "smtp_host": "smtp.mail.test",
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_build_mime_has_idempotency_and_attachment():
    msg = build_mime(
        sender="me@mail.example.com",
        to=["a@b.example.com"],
        cc=["c@d.example.com"],
        subject="Hi",
        body_text="Body",
        attachments=[Attachment("cv.pdf", "application/pdf", b"%PDF")],
        idempotency_key="k:1",
    )
    assert msg["X-LifeEasy-Idempotency"] == "k:1" and msg["Cc"] == "c@d.example.com"
    names = [p.get_filename() for p in msg.iter_attachments()]
    assert names == ["cv.pdf"]


async def test_imap_connection_stores_encrypted_password(client, auth, session, monkeypatch):
    conn = await _imap(client, auth, monkeypatch)
    assert conn["provider"] == "imap" and conn["account_email"] == "me@mail.example.com"
    row = await session.get(m.OAuthConnection, __import__("uuid").UUID(conn["id"]))
    assert row.access_token_enc and "app-password-123" not in row.access_token_enc
    assert get_secret_box().decrypt(row.access_token_enc) == "app-password-123"
    listed = (await client.get("/api/v1/email/connections", headers=auth)).json()
    assert [c["id"] for c in listed] == [conn["id"]]
    assert "access_token_enc" not in listed[0]
    assert (await client.delete(f"/api/v1/email/connections/{conn['id']}", headers=auth)).status_code == 204
    assert (await client.get("/api/v1/email/connections", headers=auth)).json() == []
    await session.rollback()  # end this session's read snapshot so the API's commit is visible
    await session.refresh(row)
    assert row.access_token_enc is None, "disconnect wipes the stored secret"


async def test_draft_uses_llm(client, auth):
    set_llm(FakeLLM(json_handler=lambda prompt, schema: {"subject": "Following up", "body": "Hello, just checking in."}))
    resp = await client.post(
        "/api/v1/email/drafts", headers=auth, json={"purpose": "follow_up", "context": "Applied to Acme last week"}
    )
    assert resp.status_code == 200 and resp.json() == {"subject": "Following up", "body": "Hello, just checking in."}


async def test_send_requires_connection(client, auth):
    resp = await client.post(
        "/api/v1/email/send", headers=auth, json={"to": ["hr@acme.example.com"], "subject": "Hi", "body": "Hello"}
    )
    assert resp.status_code == 503 and resp.json()["error"]["code"] == "provider_not_configured"


async def test_send_creates_approval_and_executes_only_after_approve(client, auth, session, monkeypatch, inline_tasks):
    conn = await _imap(client, auth, monkeypatch)
    fake = FakeProvider()

    async def _provider_for(session, c):  # noqa: ANN001
        assert str(c.id) == conn["id"]
        return fake

    monkeypatch.setattr(email_service, "provider_for", _provider_for)
    up = await client.post("/api/v1/resumes", headers=auth, files={"file": ("cv.txt", b"Python developer", "text/plain")})
    resume_id = up.json()["id"]

    resp = await client.post(
        "/api/v1/email/send",
        headers=auth,
        json={
            "to": ["HR@acme.example.com"],
            "subject": "Application",
            "body": "Please find my CV.",
            "attachments": [{"type": "resume", "resume_id": resume_id}],
        },
    )
    assert resp.status_code == 201, resp.text
    approval = resp.json()
    assert approval["status"] == "pending" and approval["destination"]["to"] == ["hr@acme.example.com"]
    assert approval["destination"]["from"] == "me@mail.example.com" and approval["attachments"][0]["filename"] == "cv.txt"
    assert fake.sent == [], "nothing is sent before approval"

    ok = await client.post(
        f"/api/v1/approvals/{approval['id']}/approve", headers=auth, json={"content_hash": approval["content_hash"]}
    )
    assert ok.status_code == 200 and ok.json()["status"] == "executed", ok.json()
    assert len(fake.sent) == 1
    sent = fake.sent[0]
    assert sent["to"] == ["hr@acme.example.com"] and sent["body"] == "Please find my CV." and sent["subject"] == "Application"
    assert sent["attachments"][0].filename == "cv.txt" and sent["attachments"][0].data == b"Python developer"
    assert ok.json()["result"]["provider"] == "imap"


async def test_send_rejects_foreign_resume(client, auth, monkeypatch):
    await _imap(client, auth, monkeypatch)
    other = await client.post("/api/v1/auth/register", json={"email": "o@example.com", "password": "correct horse battery"})
    other_auth = {"Authorization": f"Bearer {other.json()['access_token']}"}
    up = await client.post("/api/v1/resumes", headers=other_auth, files={"file": ("cv.txt", b"x", "text/plain")})
    resp = await client.post(
        "/api/v1/email/send",
        headers=auth,
        json={
            "to": ["a@b.example.com"],
            "subject": "S",
            "body": "B",
            "attachments": [{"type": "resume", "resume_id": up.json()["id"]}],
        },
    )
    assert resp.status_code == 404


async def test_oauth_start_not_configured(client, auth):
    resp = await client.get("/api/v1/connections/oauth/google/start", headers=auth)
    assert resp.status_code == 503
    assert (await client.get("/api/v1/connections/oauth/yahoo/start", headers=auth)).status_code == 404


async def test_oauth_callback_bad_state_redirects(client):
    resp = await client.get("/api/v1/connections/oauth/google/callback", params={"code": "x", "state": "bad"})
    assert resp.status_code == 302 and "error=" in resp.headers["location"]


async def test_linkedin_publish_without_connection_is_manual(client, auth, inline_tasks):
    resp = await client.post("/api/v1/linkedin/publish", headers=auth, json={"text": "Excited to share..."})
    assert resp.status_code == 201 and resp.json()["destination"]["audience"].startswith("public")
    a = resp.json()
    ok = await client.post(f"/api/v1/approvals/{a['id']}/approve", headers=auth, json={"content_hash": a["content_hash"]})
    assert ok.json()["status"] == "executed" and ok.json()["result"]["delivery"] == "manual"


async def test_audit_trail_for_send(client, auth, session, monkeypatch, inline_tasks):
    await _imap(client, auth, monkeypatch)
    monkeypatch.setattr(email_service, "provider_for", lambda s, c: _async(FakeProvider()))
    a = (
        await client.post("/api/v1/email/send", headers=auth, json={"to": ["a@b.example.com"], "subject": "S", "body": "B"})
    ).json()
    await client.post(f"/api/v1/approvals/{a['id']}/approve", headers=auth, json={"content_hash": a["content_hash"]})
    types = (await session.scalars(select(m.AuditEvent.event_type))).all()
    assert {"connection.create", "approval.create", "approval.approve", "approval.executed"} <= set(types)


async def _async(value):  # noqa: ANN001
    return value
