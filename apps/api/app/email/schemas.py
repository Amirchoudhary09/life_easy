from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field


class ConnectionOut(BaseModel):
    id: uuid.UUID
    provider: str
    account_email: str
    scopes: list[str]
    revoked_at: datetime | None
    last_error: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ImapConnectionCreate(BaseModel):
    account_email: EmailStr
    username: str | None = Field(default=None, max_length=320)
    password: str = Field(min_length=1, max_length=200)
    imap_host: str = Field(max_length=200)
    imap_port: int = Field(default=993, ge=1, le=65535)
    smtp_host: str = Field(max_length=200)
    smtp_port: int = Field(default=587, ge=1, le=65535)


class DraftRequest(BaseModel):
    purpose: Literal["application", "follow_up", "recruiter_outreach", "thank_you", "custom"] = "custom"
    to_name: str | None = Field(default=None, max_length=120)
    context: str = Field(default="", max_length=4000)
    tone: Literal["professional", "warm", "concise"] = "professional"
    application_id: uuid.UUID | None = None
    job_id: uuid.UUID | None = None


class DraftOut(BaseModel):
    subject: str
    body: str


class AttachmentRef(BaseModel):
    type: Literal["resume"] = "resume"
    resume_id: uuid.UUID


class SendRequest(BaseModel):
    connection_id: uuid.UUID | None = None
    to: list[EmailStr] = Field(min_length=1, max_length=10)
    cc: list[EmailStr] = Field(default_factory=list, max_length=10)
    subject: str = Field(min_length=1, max_length=500)
    body: str = Field(min_length=1, max_length=20000)
    attachments: list[AttachmentRef] = Field(default_factory=list, max_length=3)
    application_id: uuid.UUID | None = None


class InboxItem(BaseModel):
    id: str
    from_addr: str
    subject: str
    received_at: datetime | None
    snippet: str
    classification: dict[str, Any] | None = None
