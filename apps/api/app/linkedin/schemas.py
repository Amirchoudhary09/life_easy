from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class PostDraftRequest(BaseModel):
    topic: str = Field(min_length=3, max_length=2000)
    tone: Literal["professional", "personal", "thoughtful"] = "professional"
    length: Literal["short", "medium", "long"] = "medium"


class PostDraftOut(BaseModel):
    text: str
    hashtags: list[str]


class MessageDraftRequest(BaseModel):
    kind: Literal["connection_note", "recruiter_message", "inmail"] = "recruiter_message"
    recipient_name: str | None = Field(default=None, max_length=120)
    recipient_role: str | None = Field(default=None, max_length=120)
    company: str | None = Field(default=None, max_length=200)
    context: str = Field(default="", max_length=2000)


class MessageDraftOut(BaseModel):
    text: str


class PublishRequest(BaseModel):
    text: str = Field(min_length=1, max_length=3000)


class SendMessageRequest(BaseModel):
    recipient: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=1500)
