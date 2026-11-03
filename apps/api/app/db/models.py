"""Database models. Every user-owned table carries `user_id`; queries must always scope by it.

Table groups:
- identity: users, refresh_tokens, channel_identities, link_codes
- profile:  profiles, resumes
- jobs:     jobs, job_matches, recruiter_contacts
- tracker:  applications, application_events, interviews, follow_ups
- chat:     conversations, messages, processed_events, memory_items
- actions:  oauth_connections, action_approvals, audit_events, usage_counters
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.config import get_settings
from app.db.types import GUID, Embedding, JSONDoc, UTCDateTime

EMBEDDING_DIM = get_settings().embedding_dim


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_id() -> uuid.UUID:
    return uuid.uuid4()


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False)


# --- identity -------------------------------------------------------------------


class User(TimestampMixin, Base):
    __tablename__ = "app_users"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    display_name: Mapped[str | None] = mapped_column(String(120))
    password_hash: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    email_verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    profile: Mapped[Profile | None] = relationship(back_populates="user", uselist=False)


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(GUID, ForeignKey("app_users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class ChannelIdentity(Base):
    """A verified messaging identity (WhatsApp wa_id, Telegram chat id) bound to one user."""

    __tablename__ = "channel_identities"
    __table_args__ = (UniqueConstraint("provider", "external_id", name="uq_channel_identity"),)

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(GUID, ForeignKey("app_users.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(20), nullable=False)  # whatsapp | telegram
    external_id: Mapped[str] = mapped_column(String(100), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(120))
    verified_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class LinkCode(Base):
    """One-time code shown in the dashboard; the user sends `LINK <code>` from the channel."""

    __tablename__ = "link_codes"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(GUID, ForeignKey("app_users.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(12), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


# --- profile --------------------------------------------------------------------


class Profile(TimestampMixin, Base):
    __tablename__ = "profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(GUID, ForeignKey("app_users.id", ondelete="CASCADE"), primary_key=True)
    headline: Mapped[str | None] = mapped_column(String(200))
    summary: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(String(120))
    experience_years: Mapped[float | None] = mapped_column(Numeric(4, 1))
    skills: Mapped[list[str]] = mapped_column(JSONDoc, default=list, nullable=False)
    # preferences: {"locations": [...], "remote": "any|remote|onsite", "employment_types": [...],
    #               "salary_min": int, "currency": "INR", "titles": [...], "exclude_companies": [...]}
    preferences: Mapped[dict[str, Any]] = mapped_column(JSONDoc, default=dict, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Kolkata", nullable=False)
    digest_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Embedding(EMBEDDING_DIM))

    user: Mapped[User] = relationship(back_populates="profile")


class Resume(TimestampMixin, Base):
    __tablename__ = "resumes"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(GUID, ForeignKey("app_users.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str | None] = mapped_column(Text)  # extracted plain text
    parsed: Mapped[dict[str, Any]] = mapped_column(JSONDoc, default=dict, nullable=False)  # structured
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # tailored resumes point at the job they were written for
    tailored_for_job_id: Mapped[uuid.UUID | None] = mapped_column(GUID, ForeignKey("jobs.id", ondelete="SET NULL"))
    embedding: Mapped[list[float] | None] = mapped_column(Embedding(EMBEDDING_DIM))


# --- jobs -----------------------------------------------------------------------


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("source", "source_job_id", name="uq_job_source"),
        Index("ix_jobs_posted_at", "posted_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=new_id)
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    source_job_id: Mapped[str] = mapped_column(String(200), nullable=False)  # never null: derived if missing
    company: Mapped[str] = mapped_column(String(200), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    location: Mapped[str | None] = mapped_column(String(200))
    remote: Mapped[bool | None] = mapped_column(Boolean)
    employment_type: Mapped[str | None] = mapped_column(String(60))
    salary_text: Mapped[str | None] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    apply_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(1000))
    posted_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    fetched_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Embedding(EMBEDDING_DIM))


class JobMatch(TimestampMixin, Base):
    __tablename__ = "job_matches"

    user_id: Mapped[uuid.UUID] = mapped_column(GUID, ForeignKey("app_users.id", ondelete="CASCADE"), primary_key=True)
    job_id: Mapped[uuid.UUID] = mapped_column(GUID, ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True)
    score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)  # 0..100
    # explanation: {"summary": str, "strengths": [...], "gaps": [...], "location_ok": bool, ...}
    explanation: Mapped[dict[str, Any]] = mapped_column(JSONDoc, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="suggested", nullable=False)
    # suggested | saved | skipped | applied
    digest_sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class RecruiterContact(Base):
    """Publicly listed contact, owned by the user who researched it, with its source and a retention date."""

    __tablename__ = "recruiter_contacts"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(GUID, ForeignKey("app_users.id", ondelete="CASCADE"), index=True)
    company: Mapped[str] = mapped_column(String(200), nullable=False)
    name: Mapped[str | None] = mapped_column(String(200))
    role: Mapped[str | None] = mapped_column(String(200))
    public_email: Mapped[str | None] = mapped_column(String(320))
    public_profile_url: Mapped[str | None] = mapped_column(String(1000))
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    source_excerpt: Mapped[str | None] = mapped_column(Text)  # the evidence the contact was found in
    retrieved_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)  # retention
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


# --- tracker --------------------------------------------------------------------

APPLICATION_STATUSES = (
    "planned",
    "applied",
    "screening",
    "interview",
    "offer",
    "accepted",
    "rejected",
    "withdrawn",
)


class Application(TimestampMixin, Base):
    __tablename__ = "applications"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(GUID, ForeignKey("app_users.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[uuid.UUID | None] = mapped_column(GUID, ForeignKey("jobs.id", ondelete="SET NULL"))
    contact_id: Mapped[uuid.UUID | None] = mapped_column(GUID, ForeignKey("recruiter_contacts.id", ondelete="SET NULL"))
    company: Mapped[str] = mapped_column(String(200), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="planned", nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(1000))
    applied_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    next_follow_up_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_contact_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    notes: Mapped[str | None] = mapped_column(Text)
    resume_id: Mapped[uuid.UUID | None] = mapped_column(GUID, ForeignKey("resumes.id", ondelete="SET NULL"))


class ApplicationEvent(Base):
    __tablename__ = "application_events"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=new_id)
    application_id: Mapped[uuid.UUID] = mapped_column(GUID, ForeignKey("applications.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(GUID, ForeignKey("app_users.id", ondelete="CASCADE"), index=True)
    from_status: Mapped[str | None] = mapped_column(String(20))
    to_status: Mapped[str] = mapped_column(String(20), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(20), default="user", nullable=False)  # user | inbox | agent
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class Interview(TimestampMixin, Base):
    __tablename__ = "interviews"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(GUID, ForeignKey("app_users.id", ondelete="CASCADE"), index=True)
    application_id: Mapped[uuid.UUID] = mapped_column(GUID, ForeignKey("applications.id", ondelete="CASCADE"), index=True)
    scheduled_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    kind: Mapped[str] = mapped_column(String(40), default="interview", nullable=False)  # phone|video|onsite|test
    location: Mapped[str | None] = mapped_column(String(500))  # link or address
    notes: Mapped[str | None] = mapped_column(Text)
    prep_sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    outcome: Mapped[str | None] = mapped_column(String(40))


class FollowUp(TimestampMixin, Base):
    __tablename__ = "follow_ups"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(GUID, ForeignKey("app_users.id", ondelete="CASCADE"), index=True)
    application_id: Mapped[uuid.UUID] = mapped_column(GUID, ForeignKey("applications.id", ondelete="CASCADE"), index=True)
    due_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    # pending | drafted | sent | cancelled
    approval_id: Mapped[uuid.UUID | None] = mapped_column(GUID, ForeignKey("action_approvals.id", ondelete="SET NULL"))


# --- chat -----------------------------------------------------------------------


class Conversation(TimestampMixin, Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(GUID, ForeignKey("app_users.id", ondelete="CASCADE"), index=True)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)  # web | whatsapp | telegram
    title: Mapped[str | None] = mapped_column(String(200))
    last_message_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=new_id)
    conversation_id: Mapped[uuid.UUID] = mapped_column(GUID, ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(GUID, ForeignKey("app_users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # user | assistant | tool
    content: Mapped[str] = mapped_column(Text, nullable=False)
    meta: Mapped[dict[str, Any]] = mapped_column(JSONDoc, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class ProcessedEvent(Base):
    """Webhook delivery IDs already handled, so provider retries never run twice."""

    __tablename__ = "processed_events"
    __table_args__ = (UniqueConstraint("provider", "event_id", name="uq_processed_event"),)

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=new_id)
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    event_id: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class MemoryItem(Base):
    __tablename__ = "memory_items"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(GUID, ForeignKey("app_users.id", ondelete="CASCADE"), index=True)
    memory_type: Mapped[str] = mapped_column(String(40), nullable=False)  # preference | fact | feedback
    content: Mapped[str] = mapped_column(Text, nullable=False)
    meta: Mapped[dict[str, Any]] = mapped_column(JSONDoc, default=dict, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Embedding(EMBEDDING_DIM))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


# --- actions --------------------------------------------------------------------


class OAuthConnection(TimestampMixin, Base):
    """A connected external account (email provider). Tokens are encrypted at rest."""

    __tablename__ = "oauth_connections"
    __table_args__ = (UniqueConstraint("user_id", "provider", "account_email", name="uq_oauth_connection"),)

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(GUID, ForeignKey("app_users.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(20), nullable=False)  # google | microsoft | imap
    account_email: Mapped[str] = mapped_column(String(320), nullable=False)
    scopes: Mapped[list[str]] = mapped_column(JSONDoc, default=list, nullable=False)
    access_token_enc: Mapped[str | None] = mapped_column(Text)
    refresh_token_enc: Mapped[str | None] = mapped_column(Text)
    token_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    # imap/smtp hosts, ports; never plaintext secrets
    extra: Mapped[dict[str, Any]] = mapped_column(JSONDoc, default=dict, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_error: Mapped[str | None] = mapped_column(Text)


APPROVAL_STATUSES = ("pending", "approved", "rejected", "executing", "executed", "failed", "expired")


class ActionApproval(TimestampMixin, Base):
    """One pending external action. Approval binds to `content_hash`; any edit creates a new row."""

    __tablename__ = "action_approvals"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(GUID, ForeignKey("app_users.id", ondelete="CASCADE"), index=True)
    action_type: Mapped[str] = mapped_column(String(60), nullable=False)
    # send_email | linkedin_post | linkedin_message | submit_application | whatsapp_message
    channel: Mapped[str] = mapped_column(String(40), nullable=False)
    # destination: {"to": [...], "cc": [...], "audience": "public"} - shown verbatim in the preview
    destination: Mapped[dict[str, Any]] = mapped_column(JSONDoc, default=dict, nullable=False)
    subject: Mapped[str | None] = mapped_column(String(500))
    body: Mapped[str] = mapped_column(Text, nullable=False)
    attachments: Mapped[list[dict[str, Any]]] = mapped_column(JSONDoc, default=list, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONDoc, default=dict, nullable=False)  # executor args
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    preview_channel: Mapped[str | None] = mapped_column(String(20))  # where the preview was shown
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    rejected_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    executed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    result: Mapped[dict[str, Any]] = mapped_column(JSONDoc, default=dict, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    related_application_id: Mapped[uuid.UUID | None] = mapped_column(GUID, ForeignKey("applications.id", ondelete="SET NULL"))


class AuditEvent(Base):
    """Insert-only record of consequential actions."""

    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID | None] = mapped_column(GUID, ForeignKey("app_users.id", ondelete="SET NULL"), index=True)
    actor: Mapped[str] = mapped_column(String(20), nullable=False)  # user | agent | system
    event_type: Mapped[str] = mapped_column(String(60), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(40))
    target_id: Mapped[str | None] = mapped_column(String(64))
    details: Mapped[dict[str, Any]] = mapped_column(JSONDoc, default=dict, nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class UsageCounter(Base):
    """Per-user daily counters (LLM calls, emails sent) for plan limits and cost tracking."""

    __tablename__ = "usage_counters"
    __table_args__ = (UniqueConstraint("user_id", "day", "kind", name="uq_usage_counter"),)

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(GUID, ForeignKey("app_users.id", ondelete="CASCADE"), index=True)
    day: Mapped[str] = mapped_column(String(10), nullable=False)  # YYYY-MM-DD (UTC)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
