from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ApprovalOut(BaseModel):
    id: uuid.UUID
    action_type: str
    channel: str
    destination: dict[str, Any]
    subject: str | None
    body: str
    attachments: list[dict[str, Any]]
    content_hash: str
    status: str
    preview_channel: str | None
    expires_at: datetime
    approved_at: datetime | None
    executed_at: datetime | None
    result: dict[str, Any]
    error: str | None
    related_application_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ApproveRequest(BaseModel):
    content_hash: str = Field(min_length=64, max_length=64, description="hash shown with the preview; must match")


class RejectRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class EditRequest(BaseModel):
    subject: str | None = Field(default=None, max_length=500)
    body: str = Field(min_length=1, max_length=20000)
    destination: dict[str, Any] | None = None
