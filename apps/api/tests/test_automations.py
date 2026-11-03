from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.ai.llm import FakeLLM, set_llm
from app.automations import inbox_watch
from app.automations.digest import run_daily_digest
from app.automations.followups import run_follow_ups
from app.automations.interview_prep import run_interview_prep
from app.automations.weekly_report import run_weekly_report
from app.db import models as m
from app.email.base import InboundEmail
from app.jobs.ingest import upsert_postings
from app.jobs.sources.base import JobPosting
from sqlalchemy import select

from tests.conftest import make_user
from tests.test_email import FakeProvider


async def _linked_user(session, **profile):  # noqa: ANN001
    user = await make_user(session, **profile)
    session.add(m.ChannelIdentity(user_id=user.id, provider="whatsapp", external_id="91999"))
    await session.flush()
    return user


async def test_daily_digest_sends_best_matches_with_buttons(session, whatsapp):
    user = await _linked_user(
        session,
        headline="Python backend developer",
        skills=["python", "fastapi"],
        preferences={"titles": ["backend engineer"], "remote": "any"},
    )
    now = datetime.now(UTC)
    await upsert_postings(
        session,
        [
            JobPosting(
                source="t",
                source_job_id=str(i),
                company=f"Co{i}",
                title=f"Backend Engineer {i}",
                apply_url=f"https://c{i}.test",
                description="Python FastAPI APIs",
                posted_at=now,
            )
            for i in range(7)
        ],
    )
    await session.commit()
    result = await run_daily_digest(user.id)
    assert result == {"users": 1, "sent": 1}
    assert "top 5" in whatsapp.sent[0]["text"]
    items = [s for s in whatsapp.sent if s["buttons"]]
    assert len(items) == 5 and items[0]["buttons"][0].startswith("save:")
    # the dashboard inbox gets the same notices
    conv = await session.scalar(
        select(m.Conversation).where(m.Conversation.user_id == user.id, m.Conversation.channel == "notifications")
    )
    assert conv is not None
    # nothing is re-sent the next day for the same matches
    whatsapp.sent.clear()
    assert (await run_daily_digest(user.id))["sent"] in (0, 1)
    assert all(s["buttons"] == [] or "Backend Engineer" in s["text"] for s in whatsapp.sent)
    assert len([s for s in whatsapp.sent if s["buttons"]]) <= 2, "only matches not sent before"


async def test_follow_up_with_contact_creates_approval_preview(session, whatsapp):
    set_llm(
        FakeLLM(
            json_handler=lambda prompt, schema: {"subject": "Following up", "body": "Hi Priya, checking in on my application."}
        )
    )
    user = await _linked_user(session)
    session.add(
        m.OAuthConnection(
            user_id=user.id,
            provider="imap",
            account_email="me@mail.test",
            access_token_enc="x",
            extra={"imap_host": "h", "smtp_host": "h"},
        )
    )
    contact = m.RecruiterContact(
        user_id=user.id,
        company="Acme",
        name="Priya",
        public_email="priya@acme.test",
        source_url="https://acme.test/careers",
        expires_at=datetime.now(UTC) + timedelta(days=90),
    )
    session.add(contact)
    await session.flush()
    app = m.Application(
        user_id=user.id,
        company="Acme",
        title="SDE",
        status="applied",
        applied_at=datetime.now(UTC) - timedelta(days=8),
        next_follow_up_at=datetime.now(UTC) - timedelta(hours=1),
        contact_id=contact.id,
    )
    session.add(app)
    await session.commit()

    assert await run_follow_ups() == {"drafted": 1, "reminded": 0}
    preview = whatsapp.sent[-1]
    assert (
        "priya@acme.test" in preview["text"] and "checking in" in preview["text"] and preview["buttons"][0].startswith("approve:")
    )
    approvals = (await session.scalars(select(m.ActionApproval).where(m.ActionApproval.user_id == user.id))).all()
    assert len(approvals) == 1 and approvals[0].status == "pending", "a draft is never sent without approval"
    assert (await run_follow_ups()) == {"drafted": 0, "reminded": 0}, "no duplicate follow-up while one is open"


async def test_follow_up_without_contact_reminds(session, whatsapp):
    user = await _linked_user(session)
    session.add(
        m.Application(
            user_id=user.id,
            company="Initech",
            title="SRE",
            status="applied",
            applied_at=datetime.now(UTC) - timedelta(days=8),
            next_follow_up_at=datetime.now(UTC) - timedelta(hours=1),
        )
    )
    await session.commit()
    assert await run_follow_ups() == {"drafted": 0, "reminded": 1}
    assert "Initech" in whatsapp.sent[-1]["text"]
    app = await session.scalar(select(m.Application))
    await session.refresh(app)
    assert app.next_follow_up_at > datetime.now(UTC)


async def test_interview_prep_sent_once(session, whatsapp):
    set_llm(
        FakeLLM(
            json_handler=lambda prompt, schema: {
                "likely_questions": ["Tell me about a system you designed"],
                "questions_to_ask": ["How is on-call run?"],
                "tips": ["Be concrete"],
            }
        )
    )
    user = await _linked_user(session)
    app = m.Application(user_id=user.id, company="Acme", title="SDE", status="interview")
    session.add(app)
    await session.flush()
    session.add(
        m.Interview(user_id=user.id, application_id=app.id, scheduled_at=datetime.now(UTC) + timedelta(hours=20), kind="video")
    )
    await session.commit()
    assert await run_interview_prep() == {"sent": 1}
    assert "Interview prep: SDE at Acme" in whatsapp.sent[-1]["text"] and "system you designed" in whatsapp.sent[-1]["text"]
    assert await run_interview_prep() == {"sent": 0}


async def test_weekly_report(session, telegram):
    user = await make_user(session)
    session.add(m.ChannelIdentity(user_id=user.id, provider="telegram", external_id="42"))
    session.add(
        m.Application(user_id=user.id, company="A", title="T", status="applied", applied_at=datetime.now(UTC) - timedelta(days=1))
    )
    await session.commit()
    assert await run_weekly_report(user.id) == {"sent": 1}
    assert "Applications sent: 1" in telegram.sent[-1]["text"]


async def test_weekly_report_skips_quiet_users(session, telegram):
    await make_user(session)
    await session.commit()
    assert await run_weekly_report() == {"sent": 0}


async def test_inbox_watch_updates_tracker(session, whatsapp, monkeypatch):
    set_llm(
        FakeLLM(
            json_handler=lambda prompt, schema: {
                "category": "interview_invite",
                "company": "Acme",
                "confidence": 0.95,
                "summary": "They want to schedule a call.",
            }
        )
    )
    user = await _linked_user(session)
    session.add(
        m.OAuthConnection(
            user_id=user.id,
            provider="imap",
            account_email="me@mail.test",
            access_token_enc="x",
            extra={"imap_host": "h", "smtp_host": "h"},
        )
    )
    session.add(
        m.Application(
            user_id=user.id, company="Acme", title="SDE", status="applied", applied_at=datetime.now(UTC) - timedelta(days=3)
        )
    )
    await session.commit()
    mail = [
        InboundEmail(
            id="1",
            from_addr="Talent <talent@acme.test>",
            subject="Acme: next steps for SDE",
            received_at=datetime.now(UTC),
            snippet="We'd like to schedule an interview",
        ),
        InboundEmail(id="2", from_addr="news@shop.test", subject="Sale!", received_at=datetime.now(UTC), snippet="50% off"),
    ]

    async def _provider_for(s, c):  # noqa: ANN001
        return FakeProvider(inbox=mail)

    monkeypatch.setattr(inbox_watch, "provider_for", _provider_for)
    result = await inbox_watch.run_inbox_watch(user.id)
    assert result == {"processed": 2, "updated": 1}
    app = await session.scalar(select(m.Application))
    await session.refresh(app)
    assert app.status == "interview"
    events = (await session.scalars(select(m.ApplicationEvent).where(m.ApplicationEvent.source == "inbox"))).all()
    assert len(events) == 1
    assert "interview invite" in whatsapp.sent[-1]["text"]
