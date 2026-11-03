from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class Preferences(BaseModel):
    locations: list[str] = Field(default_factory=list)
    remote: Literal["any", "remote", "onsite", "hybrid"] = "any"
    employment_types: list[str] = Field(default_factory=lambda: ["full-time"])
    titles: list[str] = Field(default_factory=list)
    salary_min: int | None = None
    currency: str = "INR"
    exclude_companies: list[str] = Field(default_factory=list)
    digest_hour_local: int = Field(default=9, ge=0, le=23)


class ProfileOut(BaseModel):
    headline: str | None
    summary: str | None
    location: str | None
    experience_years: float | None
    skills: list[str]
    preferences: dict[str, Any]
    timezone: str
    digest_enabled: bool

    model_config = {"from_attributes": True}


class ProfileUpdate(BaseModel):
    headline: str | None = Field(default=None, max_length=200)
    summary: str | None = Field(default=None, max_length=4000)
    location: str | None = Field(default=None, max_length=120)
    experience_years: float | None = Field(default=None, ge=0, le=60)
    skills: list[str] | None = Field(default=None, max_length=100)
    preferences: Preferences | None = None
    timezone: str | None = Field(default=None, max_length=64)
    digest_enabled: bool | None = None
    display_name: str | None = Field(default=None, max_length=120)
