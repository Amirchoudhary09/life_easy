from __future__ import annotations

import hashlib
import hmac
import json

from app.ai.llm import FakeLLM, LLMResponse, ToolCall, set_llm
from app.approvals import service as approvals
from app.channels.base import chunk_text
from app.channels.linking import create_link_code, parse_link_command
from app.channels.pipeline import handle_inbound
from app.channels.telegram import TelegramAdapter
from app.channels.whatsapp import WhatsAppAdapter
from app.db import models as m
from app.tasks.runner import inline_calls
from sqlalchemy import select

from tests.conftest import make_user


@approvals.register_executor("chat_test")
async def _exec(session, approval):  # noqa: ANN001
    return {"ok": True}


def _wa_payload(sender: str = "919999999999", text: str = "hello", mid: str = "wamid.1", button: str | None = None) -> dict:
    msg: dict = {"from": sender, "id": mid, "timestamp": "1", "type": "text", "text": {"body": text}}
    if button:
        msg = {
            "from": sender,
            "id": mid,
            "timestamp": "1",
            "type": "interactive",
            "interactive": {"type": "button_reply", "button_reply": {"id": button, "title": "Approve"}},
        }
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "1",
                "changes": [
                    {
                        "field": "messages",
                        "value": {"contacts": [{"wa_id": sender, "profile": {"name": "Amir"}}], "messages": [msg]},
                    }
                ],
            }
        ],
    }


def _sign(body: bytes, secret: str = "app-secret") -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_whatsapp_parse_text_and_buttons():
    adapter = WhatsAppAdapter()
    msgs = adapter.parse(_wa_payload())
    assert len(msgs) == 1
    assert msgs[0].external_id == "919999999999" and msgs[0].text == "hello" and msgs[0].display_name == "Amir"
    btn = adapter.parse(_wa_payload(button="approve:abc"))[0]
    assert btn.button_id == "approve:abc"
    assert adapter.parse({"entry": [{"changes": [{"field": "statuses", "value": {}}]}]}) == []


def test_whatsapp_signature():
    adapter = WhatsAppAdapter()
    body = b'{"x":1}'
    assert adapter.valid_signature(body, _sign(body))
    assert not adapter.valid_signature(body, _sign(body, "other"))
    assert not adapter.valid_signature(body + b" ", _sign(body))
    assert not adapter.valid_signature(body, None)


def test_telegram_parse():
    adapter = TelegramAdapter()
    msg = adapter.parse(
        {"update_id": 7, "message": {"message_id": 3, "chat": {"id": 42}, "from": {"first_name": "Amir"}, "text": "/start"}}
    )[0]
    assert msg.external_id == "42" and msg.text == "hello" and msg.event_id == "u7"
    cb = adapter.parse(
        {
            "update_id": 8,
            "callback_query": {
                "id": "cb1",
                "data": "approve:x",
                "from": {"first_name": "A"},
                "message": {"message_id": 9, "chat": {"id": 42}},
            },
        }
    )[0]
    assert cb.button_id == "approve:x" and cb.reply_to["callback_query_id"] == "cb1"
    assert adapter.parse({"update_id": 9, "edited_message": {}}) == []


def test_link_command_and_chunking():
    assert parse_link_command("LINK ab12cd") == "AB12CD"
    assert parse_link_command("/link AB12CD ") == "AB12CD"
    assert parse_link_command("link me please") is None
    chunks = chunk_text("word " * 2000, 1000)
    assert all(len(c) <= 1000 for c in chunks) and "".join(chunks).replace(" ", "") == ("word" * 2000)


async def test_whatsapp_webhook_verify_and_receive(client, whatsapp):
    ok = await client.get(
        "/api/v1/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "verify-token", "hub.challenge": "123"}
    )
    assert ok.status_code == 200 and ok.text == "123"
    bad = await client.get(
        "/api/v1/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "nope", "hub.challenge": "123"}
    )
    assert bad.status_code == 403

    body = json.dumps(_wa_payload()).encode()
    unsigned = await client.post("/api/v1/webhooks/whatsapp", content=body, headers={"content-type": "application/json"})
    assert unsigned.status_code == 401
    forged = await client.post(
        "/api/v1/webhooks/whatsapp",
        content=body,
        headers={"content-type": "application/json", "x-hub-signature-256": _sign(body, "wrong")},
    )
    assert forged.status_code == 401
    signed = await client.post(
        "/api/v1/webhooks/whatsapp",
        content=body,
        headers={"content-type": "application/json", "x-hub-signature-256": _sign(body)},
    )
    assert signed.status_code == 200 and signed.json()["message_events_received"] == 1
    name, kwargs = inline_calls()[-1]
    assert name == "process_inbound_message" and kwargs["external_id"] == "919999999999" and kwargs["channel"] == "whatsapp"


async def test_telegram_webhook_secret(client, telegram):
    payload = {"update_id": 1, "message": {"message_id": 1, "chat": {"id": 5}, "from": {"first_name": "A"}, "text": "hi"}}
    assert (await client.post("/api/v1/webhooks/telegram", json=payload)).status_code == 401
    assert (
        await client.post("/api/v1/webhooks/telegram", json=payload, headers={"X-Telegram-Bot-Api-Secret-Token": "bad"})
    ).status_code == 401
    ok = await client.post("/api/v1/webhooks/telegram", json=payload, headers={"X-Telegram-Bot-Api-Secret-Token": "tg-secret"})
    assert ok.status_code == 200 and ok.json()["message_events_received"] == 1


async def test_pipeline_link_then_chat_then_approve(session, whatsapp, inline_tasks):
    user = await make_user(session)
    code = await create_link_code(session, user.id)
    await session.commit()

    r = await handle_inbound(channel="whatsapp", external_id="91999", text="hello", event_id="e1", display_name="Amir")
    assert r["status"] == "not_linked" and "LINK" in whatsapp.sent[-1]["text"]

    r = await handle_inbound(channel="whatsapp", external_id="91999", text="link WRONG1", event_id="e1b")
    assert r["status"] == "link_failed"

    r = await handle_inbound(
        channel="whatsapp", external_id="91999", text=f"link {code.code}", event_id="e2", display_name="Amir"
    )
    assert r["status"] == "linked" and "Linked" in whatsapp.sent[-1]["text"]
    assert (await handle_inbound(channel="whatsapp", external_id="91999", text="x", event_id="e2"))["status"] == "duplicate"

    r = await handle_inbound(channel="whatsapp", external_id="91999", text="help", event_id="e3")
    assert r["status"] == "command" and "approval" in whatsapp.sent[-1]["text"]

    # the agent (fake LLM) answers a normal message, and the conversation is stored for this user only
    r = await handle_inbound(channel="whatsapp", external_id="91999", text="find me python jobs", event_id="e4")
    assert r["status"] == "replied" and "[fake-llm]" in whatsapp.sent[-1]["text"]
    msgs = (await session.scalars(select(m.Message).where(m.Message.user_id == user.id))).all()
    assert {x.role for x in msgs} == {"user", "assistant"}

    # approve with a button
    approval = await approvals.create_approval(
        session, user.id, action_type="chat_test", channel="test", destination={"to": ["x@y.z"]}, subject="S", body="B"
    )
    await session.commit()
    r = await handle_inbound(
        channel="whatsapp", external_id="91999", text="", event_id="e5", button_id=f"approve:{approval.id.hex}"
    )
    assert r["status"] == "command" and "Approved" in whatsapp.sent[-1]["text"]
    await session.refresh(approval)
    assert approval.status == "executed"

    # reject by typing the short id
    approval2 = await approvals.create_approval(
        session, user.id, action_type="chat_test", channel="test", destination={}, subject=None, body="C"
    )
    await session.commit()
    r = await handle_inbound(channel="whatsapp", external_id="91999", text=f"REJECT {approval2.id.hex[:8]}", event_id="e6")
    assert "Rejected" in whatsapp.sent[-1]["text"]
    await session.refresh(approval2)
    assert approval2.status == "rejected"


async def test_other_users_approval_cannot_be_approved_from_chat(session, whatsapp, inline_tasks):
    owner = await make_user(session, "owner@example.com")
    attacker = await make_user(session, "attacker@example.com")
    session.add(m.ChannelIdentity(user_id=attacker.id, provider="whatsapp", external_id="666"))
    approval = await approvals.create_approval(
        session, owner.id, action_type="chat_test", channel="test", destination={}, subject=None, body="mine"
    )
    await session.commit()
    await handle_inbound(channel="whatsapp", external_id="666", text="", event_id="x1", button_id=f"approve:{approval.id.hex}")
    assert "couldn't find" in whatsapp.sent[-1]["text"]
    await session.refresh(approval)
    assert approval.status == "pending"


async def test_agent_tool_round_trip_creates_approval_preview(session, whatsapp, inline_tasks):
    """The LLM asks for request_send_email; the pipeline shows a preview with Approve/Reject buttons; nothing is sent."""
    user = await make_user(session)
    session.add(m.ChannelIdentity(user_id=user.id, provider="whatsapp", external_id="91999"))
    session.add(
        m.OAuthConnection(
            user_id=user.id,
            provider="imap",
            account_email="me@mail.test",
            access_token_enc="enc",
            extra={"imap_host": "h", "smtp_host": "h"},
        )
    )
    await session.commit()

    def handler(system, messages, tools):
        if messages[-1]["role"] == "user" and isinstance(messages[-1]["content"], str):
            return LLMResponse(
                text="Preparing it.",
                tool_calls=[
                    ToolCall(
                        id="t1",
                        name="request_send_email",
                        input={"to": ["hr@acme.test"], "subject": "Application", "body": "Dear HR"},
                    )
                ],
            )
        assert messages[-1]["content"][0]["type"] == "tool_result"
        return LLMResponse(text="I've prepared the email; approve it to send.")

    set_llm(FakeLLM(complete_handler=handler))
    r = await handle_inbound(channel="whatsapp", external_id="91999", text="email acme hr", event_id="e1")
    assert r["status"] == "replied" and r["approvals"] == 1 and "request_send_email" in r["tools"]
    preview = whatsapp.sent[-1]
    assert preview["buttons"][0].startswith("approve:")
    assert "hr@acme.test" in preview["text"] and "Dear HR" in preview["text"] and "me@mail.test" in preview["text"]
    pending = (await session.scalars(select(m.ActionApproval).where(m.ActionApproval.user_id == user.id))).all()
    assert len(pending) == 1 and pending[0].status == "pending"


async def test_agent_unknown_tool_and_bad_args_do_not_crash(session, whatsapp):
    user = await make_user(session)
    session.add(m.ChannelIdentity(user_id=user.id, provider="whatsapp", external_id="1"))
    await session.commit()
    calls = {"n": 0}

    def handler(system, messages, tools):
        calls["n"] += 1
        if calls["n"] == 1:
            return LLMResponse(
                tool_calls=[
                    ToolCall(id="a", name="no_such_tool", input={}),
                    ToolCall(id="b", name="set_job_status", input={"job_id": "not-a-uuid", "status": "saved"}),
                ]
            )
        results = messages[-1]["content"]
        assert "unknown tool" in results[0]["content"] and "error" in results[1]["content"]
        return LLMResponse(text="Sorry, that didn't work.")

    set_llm(FakeLLM(complete_handler=handler))
    r = await handle_inbound(channel="whatsapp", external_id="1", text="save job xyz", event_id="z1")
    assert r["status"] == "replied" and whatsapp.sent[-1]["text"] == "Sorry, that didn't work."


async def test_link_code_and_channels_api(client, auth, session, telegram, inline_tasks):
    resp = await client.post("/api/v1/channels/link-code", headers=auth)
    assert resp.status_code == 200 and len(resp.json()["code"]) == 6
    assert (await client.get("/api/v1/channels", headers=auth)).json() == []
    await handle_inbound(
        channel="telegram", external_id="4242", text=f"LINK {resp.json()['code']}", event_id="t1", display_name="Amir"
    )
    channels = (await client.get("/api/v1/channels", headers=auth)).json()
    assert len(channels) == 1 and channels[0]["provider"] == "telegram" and channels[0]["external_id_hint"] == "...4242"
    assert (await client.delete(f"/api/v1/channels/{channels[0]['id']}", headers=auth)).status_code == 204
    assert (await client.get("/api/v1/channels", headers=auth)).json() == []


async def test_stop_unlinks_chat(session, whatsapp):
    user = await make_user(session)
    session.add(m.ChannelIdentity(user_id=user.id, provider="whatsapp", external_id="777"))
    await session.commit()
    r = await handle_inbound(channel="whatsapp", external_id="777", text="STOP", event_id="s1")
    assert r["status"] == "opted_out" and "unlinked" in whatsapp.sent[-1]["text"]
    r = await handle_inbound(channel="whatsapp", external_id="777", text="hello", event_id="s2")
    assert r["status"] == "not_linked"
