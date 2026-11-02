from __future__ import annotations
from contextlib import asynccontextmanager
import json
import asyncpg
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic_settings import BaseSettings, SettingsConfigDict
from app.approvals import router as approvals_router
from app.auth import router as auth_router
from app.profile import router as profile_router
from app.jobs import router as jobs_router
from app.whatsapp import router as whatsapp_router
from app.verification import router as verification_router
from app.resumes import router as resumes_router
from app.applications import router as applications_router
from app.memories import router as memories_router
from app.assistant import router as assistant_router
from app.oauth import router as integrations_router

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_name: str = "Life Easy API"
    environment: str = "development"
    frontend_origin: str = "http://localhost:3000"
    database_url: str = ""
    redis_url: str = ""

settings = Settings()

async def init_connection(connection: asyncpg.Connection) -> None:
    await connection.set_type_codec("json", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")
    await connection.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")

@asynccontextmanager
async def lifespan(application: FastAPI):
    application.state.db = None
    if settings.database_url:
        application.state.db = await asyncpg.create_pool(dsn=settings.database_url,min_size=1,max_size=10,command_timeout=30,init=init_connection)
    yield
    if application.state.db is not None:
        await application.state.db.close()

app=FastAPI(title=settings.app_name,version="0.4.0",lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origins=[settings.frontend_origin],allow_credentials=True,allow_methods=["GET","POST","PUT","PATCH","DELETE","OPTIONS"],allow_headers=["Authorization","Content-Type","X-Request-ID"])
for router in (auth_router,profile_router,jobs_router,approvals_router,whatsapp_router,verification_router,resumes_router,applications_router,memories_router,assistant_router,integrations_router):
    app.include_router(router)

@app.get("/health")
async def health():
    return {"status":"ok","service":"life-easy-api","database_configured":bool(settings.database_url)}
