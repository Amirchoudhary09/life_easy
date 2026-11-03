from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Status = Literal["planned", "applied", "screening", "interview", "offer", "accepted", "rejected", "withdrawn"]


class ApplicationCreate(BaseModel):
    job_id: uuid.UUID | None = None
    company: str | None = Field(default=None, max_length=200)
    title: str | None = Field(default=None, max_length=300)
    status: Status = "planned"
    source_url: str | None = Field(default=None, max_length=1000)
    notes: str | None = Field(default=None, max_length=4000)


class ApplicationUpdate(BaseModel):
    status: Status | None = None
    note: str | None = Field(default=None, max_length=4000)
    notes: str | None = Field(default=None, max_length=4000)
    next_follow_up_at: datetime | None = None
    resume_id: uuid.UUID | None = None


class ApplicationOut(BaseModel):
    id: uuid.UUID
    job_id: uuid.UUID | None
    company: str
    title: str
    status: str
    source_url: str | None
    applied_at: datetime | None
    next_follow_up_at: datetime | None
    last_contact_at: datetime | None
    notes: str | None
    resume_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class EventOut(BaseModel):
    id: uuid.UUID
    from_status: str | None
    to_status: str
    note: str | None
    source: str
    created_at: datetime

    model_config = {"from_attributes": True}


class InterviewCreate(BaseModel):
    scheduled_at: datetime
    kind: str = Field(default="interview", max_length=40)
    location: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=4000)


class InterviewUpdate(BaseModel):
    scheduled_at: datetime | None = None
    kind: str | None = Field(default=None, max_length=40)
    location: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=4000)
    outcome: str | None = Field(default=None, max_length=40)


class InterviewOut(BaseModel):
    id: uuid.UUID
    application_id: uuid.UUID
    scheduled_at: datetime
    kind: str
    location: str | None
    notes: str | None
    prep_sent_at: datetime | None
    outcome: str | None

    model_config = {"from_attributes": True}


class FollowUpCreate(BaseModel):
    due_at: datetime


class FollowUpOut(BaseModel):
    id: uuid.UUID
    application_id: uuid.UUID
    due_at: datetime
    status: str
    approval_id: uuid.UUID | None

    model_config = {"from_attributes": True}


class StatsOut(BaseModel):
    by_status: dict[str, int]
    applied_last_7_days: int
    interviews_upcoming: int
    follow_ups_due: int
