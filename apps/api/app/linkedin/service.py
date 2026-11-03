"""LinkedIn: drafts always; publishing only through the official API after approval, else copy-to-paste.

LinkedIn offers no member-to-member messaging API, so recruiter messages and
connection notes are drafted and handed back for the user to paste. Posts can
go through the Posts API when the user has connected LinkedIn (w_member_social).
No scraping, no session cookies, no browser automation.
"""

from __future__ import annotations

import uuid
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.llm import get_llm, untrusted
from app.ai.usage import charge, ensure_within_limit
from app.approvals.service import create_approval, register_executor
from app.core.errors import ProviderError
from app.db import models as m
from app.email.oauth import ensure_access_token
from app.email.service import candidate_summary, list_connections

POST_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"text": {"type": "string"}, "hashtags": {"type": "array", "items": {"type": "string"}}},
    "required": ["text"],
}
MESSAGE_SCHEMA: dict[str, Any] = {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}

LINKEDIN_VERSION = "202411"


async def draft_post(session: AsyncSession, user_id: uuid.UUID, *, topic: str, tone: str, length: str) -> dict[str, Any]:
    await ensure_within_limit(session, user_id)
    words = {"short": 80, "medium": 160, "long": 260}.get(length, 160)
    system = (
        f"You write LinkedIn posts for a job seeker in a {tone} tone, about {words} words, first person, "
        "specific and credible, no clickbait, no claims the profile does not support, 3-5 relevant hashtags."
    )
    prompt = (
        "CANDIDATE:\n"
        + untrusted(await candidate_summary(session, user_id), "candidate_profile")
        + "\n\nTOPIC:\n"
        + untrusted(topic, "user_notes")
    )
    data = await get_llm().json(system=system, prompt=prompt, schema=POST_SCHEMA, max_tokens=700)
    await charge(session, user_id, "llm")
    return {"text": str(data.get("text") or "").strip(), "hashtags": [str(h) for h in data.get("hashtags", [])][:6]}


async def draft_message(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    kind: str,
    recipient_name: str | None,
    recipient_role: str | None,
    company: str | None,
    context: str,
) -> dict[str, str]:
    await ensure_within_limit(session, user_id)
    limits = {"connection_note": 300, "recruiter_message": 900, "inmail": 1200}
    max_chars = limits.get(kind, 900)
    system = (
        f"You write a LinkedIn {kind.replace('_', ' ')} for a job seeker: polite, specific, first person, "
        f"at most {max_chars} characters, no flattery, one clear ask. Only use facts from the candidate profile."
    )
    prompt = (
        f"RECIPIENT: {recipient_name or 'unknown'} ({recipient_role or 'role unknown'}) at {company or 'company unknown'}\n"
        + "CANDIDATE:\n"
        + untrusted(await candidate_summary(session, user_id), "candidate_profile")
        + "\n\nCONTEXT:\n"
        + untrusted(context, "user_notes")
    )
    data = await get_llm().json(system=system, prompt=prompt, schema=MESSAGE_SCHEMA, max_tokens=500)
    await charge(session, user_id, "llm")
    return {"text": str(data.get("text") or "").strip()[:max_chars]}


async def request_publish(
    session: AsyncSession, user_id: uuid.UUID, *, text: str, preview_channel: str | None, actor: str = "user"
) -> m.ActionApproval:
    return await create_approval(
        session,
        user_id,
        action_type="linkedin_post",
        channel="linkedin",
        destination={"audience": "public - your LinkedIn feed"},
        subject=None,
        body=text,
        preview_channel=preview_channel,
        actor=actor,
    )


async def request_message(
    session: AsyncSession, user_id: uuid.UUID, *, recipient: str, text: str, preview_channel: str | None, actor: str = "user"
) -> m.ActionApproval:
    return await create_approval(
        session,
        user_id,
        action_type="linkedin_message",
        channel="linkedin",
        destination={"recipient": recipient},
        subject=None,
        body=text,
        preview_channel=preview_channel,
        actor=actor,
    )


@register_executor("linkedin_post")
async def _publish_post(session: AsyncSession, approval: m.ActionApproval) -> dict[str, Any]:
    conns = await list_connections(session, approval.user_id, providers=("linkedin",))
    conn = next((c for c in conns if (c.extra or {}).get("person_urn")), None)
    if conn is None:
        # No authorized API connection: the approved text is handed back for the user to paste.
        return {"delivery": "manual", "text": approval.body}
    token = await ensure_access_token(session, conn)
    payload = {
        "author": conn.extra["person_urn"],
        "commentary": approval.body,
        "visibility": "PUBLIC",
        "distribution": {"feedDistribution": "MAIN_FEED", "targetEntities": [], "thirdPartyDistributionChannels": []},
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "LinkedIn-Version": LINKEDIN_VERSION,
        "X-Restli-Protocol-Version": "2.0.0",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post("https://api.linkedin.com/rest/posts", json=payload, headers=headers)
    if resp.is_error:
        raise ProviderError(f"LinkedIn publish failed with HTTP {resp.status_code}")
    return {"delivery": "api", "post_id": resp.headers.get("x-restli-id", "")}


@register_executor("linkedin_message")
async def _deliver_message(session: AsyncSession, approval: m.ActionApproval) -> dict[str, Any]:
    return {"delivery": "manual", "text": approval.body, "recipient": approval.destination.get("recipient", "")}
