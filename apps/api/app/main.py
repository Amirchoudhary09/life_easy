from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import asyncpg
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.approvals import router as approvals_router
from app.auth import current_user, router as auth_router
from app.profile import router as profile_router
from app.whatsapp import router as whatsapp_router


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_name: str = "Life Easy API"
    environment: str = "development"
    frontend_origin: str = "http://localhost:3000"
    database_url: str = ""
    redis_url: str = ""


settings = Settings()


@asynccontextmanager
async def lifespan(application: FastAPI):
    application.state.db = None
    if settings.database_url:
        application.state.db = await asyncpg.create_pool(
            dsn=settings.database_url,
            min_size=1,
            max_size=10,
            command_timeout=30,
        )
    yield
    if application.state.db is not None:
        await application.state.db.close()


app = FastAPI(title=settings.app_name, version="0.3.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)
app.include_router(auth_router)
app.include_router(profile_router)
app.include_router(approvals_router)
app.include_router(whatsapp_router)


class JobSearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=300)
    locations: list[str] = Field(default_factory=lambda: ["India"])
    experience: str = "0-2 years"
    employment_types: list[str] = Field(default_factory=lambda: ["full-time", "internship"])
    limit: int = Field(default=20, ge=1, le=50)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "life-easy-api", "version": "0.3.0"}


@app.post("/api/v1/jobs/search")
async def search_jobs(request: JobSearchRequest, user=Depends(current_user)) -> dict[str, Any]:
    # This endpoint is authenticated and user-scoped. Provider adapters are the next build phase.
    return {
        "status": "job_sources_not_configured",
        "user_id": str(user["id"]),
        "request": request.model_dump(),
        "jobs": [],
        "message": "Job-source adapters are not connected yet. No live results are being claimed.",
    }
