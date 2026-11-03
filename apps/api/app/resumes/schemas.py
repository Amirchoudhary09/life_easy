from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ResumeOut(BaseModel):
    id: uuid.UUID
    filename: str
    content_type: str
    size_bytes: int
    is_primary: bool
    parsed: dict[str, Any]
    tailored_for_job_id: uuid.UUID | None
    has_text: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}


class TailorRequest(BaseModel):
    job_id: uuid.UUID
    resume_id: uuid.UUID | None = None
    notes: str | None = Field(default=None, max_length=2000)


class TailorOut(BaseModel):
    resume: ResumeOut
    markdown: str
    ats: dict[str, Any]
