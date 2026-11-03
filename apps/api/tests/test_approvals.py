from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from app.approvals import service
from app.core.errors import Conflict
from app.db import models as m
from sqlalchemy import select

from tests.conftest import make_user, register

RESULTS: list[dict[str, Any]] = []


@service.register_executor("test_action")
async def _fake_executor(session, approval):  # noqa: ANN001
    RESULTS.append({"id": str(approval.id), "body": approval.body})
    return {"delivered": True}


@service.register_executor("failing_action")
async def _failing_executor(session, approval):  # noqa: ANN001
    raise RuntimeError("provider down")


async def _approval(session, user, **kw) -> m.ActionApproval:  # noqa: ANN001
    base = dict(action_type="test_action", channel="test", destination={"to": ["r@x.y"]}, subject="S", body="B")
    base.update(kw)
    return await service.create_approval(session, user.id, **base)


def test_hash_binds_exact_content():
    base = dict(
        action_type="send_email",
        channel="email:a@b.c",
        destination={"to": ["r@x.y"], "cc": []},
        subject="Hi",
        body="Hello",
        attachments=[],
    )
    h1 = service.compute_hash(**base)
    assert h1 == service.compute_hash(**base)
    assert h1 != service.compute_hash(**{**base, "body": "Hello!"})
    assert h1 != service.compute_hash(**{**base, "subject": "Hi!"})
    assert h1 != service.compute_hash(**{**base, "destination": {"to": ["other@x.y"], "cc": []}})
    assert h1 != service.compute_hash(**{**base, "channel": "email:other@b.c"})
    assert h1 != service.compute_hash(**{**base, "attachments": [{"type": "resume", "resume_id": "1"}]})


async def test_preview_shows_everything(session):
    user = await make_user(session)
    a = await _approval(
        session, user, destination={"to": ["r@x.y"], "cc": ["c@x.y"]}, attachments=[{"type": "resume", "filename": "cv.pdf"}]
    )
    text = service.preview_text(a)
    for part in ("r@x.y", "c@x.y", "Subject: S", "B", "cv.pdf", f"APPROVE {a.id.hex[:8]}"):
        assert part in text


async def test_empty_body_refused(session):
    user = await make_user(session)
    with pytest.raises(Exception, match="empty"):
        await _approval(session, user, body="   ")


async def test_create_approve_execute_flow(session, inline_tasks):
    user = await make_user(session)
    approval = await _approval(session, user)
    await session.commit()
    assert approval.status == "pending"
    again = await _approval(session, user)
    assert again.id == approval.id, "identical pending content is not duplicated"

    RESULTS.clear()
    approved = await service.approve(session, user.id, approval, expected_hash=approval.content_hash, via="web")
    assert approved.status == "executed", approved.error
    assert approved.result == {"delivered": True}
    assert len(RESULTS) == 1 and RESULTS[0]["body"] == "B"
    events = (await session.scalars(select(m.AuditEvent).where(m.AuditEvent.user_id == user.id))).all()
    assert {e.event_type for e in events} >= {"approval.create", "approval.approve", "approval.executed"}

    # running the worker again for the same approval does nothing
    assert (await service.execute(approval.id))["skipped"] is True
    assert len(RESULTS) == 1


async def test_failed_execution_is_recorded(session, inline_tasks):
    user = await make_user(session)
    approval = await _approval(session, user, action_type="failing_action")
    await session.commit()
    out = await service.approve(session, user.id, approval, expected_hash=None, via="web")
    assert out.status == "failed" and "provider down" in (out.error or "")


async def test_wrong_hash_and_double_approve_rejected(session, inline_tasks):
    user = await make_user(session)
    approval = await _approval(session, user, body="X")
    await session.commit()
    with pytest.raises(Conflict, match="changed since the preview"):
        await service.approve(session, user.id, approval, expected_hash="0" * 64, via="web")
    await service.approve(session, user.id, approval, expected_hash=None, via="whatsapp")
    with pytest.raises(Conflict, match="not pending"):
        await service.approve(session, user.id, approval, expected_hash=None, via="whatsapp")


async def test_other_user_cannot_approve(session):
    owner = await make_user(session, "owner@example.com")
    intruder = await make_user(session, "intruder@example.com")
    approval = await _approval(session, owner)
    with pytest.raises(Exception, match="not found"):
        await service.approve(session, intruder.id, approval, expected_hash=None, via="web")


async def test_edit_creates_new_pending_and_rejects_old(session):
    user = await make_user(session)
    approval = await _approval(session, user, body="old")
    new = await service.edit(session, user.id, approval, subject=None, body="new", destination=None, via="web")
    assert approval.status == "rejected"
    assert new.status == "pending" and new.body == "new" and new.id != approval.id
    assert new.content_hash != approval.content_hash
    assert new.destination == approval.destination


async def test_expiry(session):
    user = await make_user(session)
    approval = await _approval(session, user, body="late")
    approval.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    await session.commit()
    assert await service.expire_stale() == 1
    await session.refresh(approval)
    assert approval.status == "expired"


async def test_expired_cannot_be_approved(session):
    user = await make_user(session)
    approval = await _approval(session, user, body="late")
    approval.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    with pytest.raises(Conflict, match="expired"):
        await service.approve(session, user.id, approval, expected_hash=None, via="web")


async def test_api_approve_requires_hash(client, auth, session, inline_tasks):
    me = await client.get("/api/v1/auth/me", headers=auth)
    user_id = uuid.UUID(me.json()["id"])
    approval = await service.create_approval(
        session, user_id, action_type="test_action", channel="test", destination={}, subject=None, body="via api"
    )
    await session.commit()
    listed = await client.get("/api/v1/approvals?status=pending", headers=auth)
    assert [a["id"] for a in listed.json()] == [str(approval.id)]
    bad = await client.post(f"/api/v1/approvals/{approval.id}/approve", headers=auth, json={"content_hash": "f" * 64})
    assert bad.status_code == 409
    ok = await client.post(f"/api/v1/approvals/{approval.id}/approve", headers=auth, json={"content_hash": approval.content_hash})
    assert ok.status_code == 200
    assert ok.json()["status"] == "executed"

    other = await register(client, "other@example.com")
    assert (await client.get(f"/api/v1/approvals/{approval.id}", headers=other)).status_code == 404
    assert (await client.get("/api/v1/approvals", headers=other)).json() == []


async def test_api_edit_and_reject(client, auth, session):
    user_id = uuid.UUID((await client.get("/api/v1/auth/me", headers=auth)).json()["id"])
    approval = await service.create_approval(
        session, user_id, action_type="test_action", channel="test", destination={"to": ["a@b.c"]}, subject="S", body="draft"
    )
    await session.commit()
    edited = await client.post(f"/api/v1/approvals/{approval.id}/edit", headers=auth, json={"body": "better draft"})
    assert edited.status_code == 201 and edited.json()["body"] == "better draft" and edited.json()["status"] == "pending"
    old = await client.get(f"/api/v1/approvals/{approval.id}", headers=auth)
    assert old.json()["status"] == "rejected"
    rej = await client.post(f"/api/v1/approvals/{edited.json()['id']}/reject", headers=auth, json={"reason": "not now"})
    assert rej.status_code == 200 and rej.json()["status"] == "rejected"
