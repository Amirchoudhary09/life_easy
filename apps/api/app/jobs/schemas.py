from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class JobOut(BaseModel):
    id: uuid.UUID
    source: str
    company: str
    title: str
    location: str | None
    remote: bool | None
    employment_type: str | None
    salary_text: str | None
    apply_url: str
    source_url: str | None
    posted_at: datetime | None
    fetched_at: datetime
    description: str | None = None

    model_config = {"from_attributes": True}


class JobSummary(BaseModel):
    id: uuid.UUID
    source: str
    company: str
    title: str
    location: str | None
    remote: bool | None
    employment_type: str | None
    salary_text: str | None
    apply_url: str
    posted_at: datetime | None

    model_config = {"from_attributes": True}


class MatchOut(BaseModel):
    job: JobSummary
    score: float
    explanation: dict[str, Any]
    status: str
    updated_at: datetime


class MatchStatusUpdate(BaseModel):
    status: Literal["saved", "skipped", "applied", "suggested"]


class IngestRequest(BaseModel):
    sources: list[str] | None = Field(default=None, max_length=10)
