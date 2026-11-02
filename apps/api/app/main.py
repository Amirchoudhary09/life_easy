from __future__ import annotations
from contextlib import asynccontextmanager
from typing import Any
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.whatsapp import router as whatsapp_router

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_name: str = "Life Easy API"
    environment: str = "development"
    frontend_origin: str = "http://localhost:3000"
    app_api_key: str = ""
    database_url: str = ""
    redis_url: str = ""

settings = Settings()

@asynccontextmanager
async def lifespan(_: FastAPI):
    yield

app = FastAPI(title=settings.app_name, version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)
app.include_router(whatsapp_router)

class JobSearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=300)
    locations: list[str] = Field(default_factory=lambda: ["India"])
    experience: str = "0-2 years"
    employment_types: list[str] = Field(default_factory=lambda: ["full-time", "internship"])
    limit: int = Field(default=20, ge=1, le=50)

class ApprovalRequest(BaseModel):
    action: str = Field(min_length=3, max_length=80)
    payload: dict[str, Any]

def require_api_key(authorization: str | None) -> None:
    if not settings.app_api_key:
        if settings.environment == "production":
            raise HTTPException(status_code=503, detail="API authentication is not configured")
        return
    if authorization != f"Bearer {settings.app_api_key}":
        raise HTTPException(status_code=401, detail="Invalid API key")

@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "life-easy-api"}

@app.get("/api/v1/me")
async def me(authorization: str | None = Header(default=None)) -> dict[str, str]:
    require_api_key(authorization)
    return {"name": "Life Easy user", "profile_status": "not_configured"}

@app.post("/api/v1/jobs/search")
async def search_jobs(request: JobSearchRequest, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    require_api_key(authorization)
    return {
        "status": "source_adapters_not_configured",
        "request": request.model_dump(),
        "jobs": [],
        "message": "Configure permitted job-source adapters to enable discovery.",
    }

@app.post("/api/v1/approvals")
async def create_approval(request: ApprovalRequest, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    require_api_key(authorization)
    return {
        "status": "pending_implementation",
        "action": request.action,
        "requires_confirmation": True,
        "message": "Approval persistence and execution worker are not configured yet.",
    }
