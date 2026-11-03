"""Life Easy API entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.core.errors import AppError
from app.core.logging import configure_logging, get_logger
from app.core.request_id import RequestIDMiddleware
from app.db.session import create_all_for_dev, dispose_engine
from app.tasks.runner import close_pool

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):  # type: ignore[no-untyped-def]
    settings = get_settings()
    configure_logging(settings.log_level, json_output=settings.is_production)
    problems = settings.production_problems()
    if problems:
        raise RuntimeError("Refusing to start in production: " + "; ".join(problems))
    if settings.is_sqlite and settings.environment != "test":
        await create_all_for_dev()  # Postgres uses Alembic migrations instead
    log.info("api started", environment=settings.environment, llm=settings.llm_provider)
    try:
        yield
    finally:
        await close_pool()
        await dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.3.0",
        lifespan=lifespan,
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
    )

    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )

    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message, **exc.extra}},
        )

    @app.get("/health", tags=["ops"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "life-easy-api"}

    from app.applications.router import router as applications_router
    from app.approvals.router import router as approvals_router
    from app.auth.router import router as auth_router
    from app.channels.router import router as channels_router
    from app.chat.router import router as chat_router
    from app.email.router import router as email_router
    from app.jobs.router import router as jobs_router
    from app.linkedin.router import router as linkedin_router
    from app.me.router import router as me_router
    from app.resumes.router import router as resumes_router

    for r in (
        auth_router,
        me_router,
        resumes_router,
        jobs_router,
        applications_router,
        approvals_router,
        email_router,
        linkedin_router,
        channels_router,
        chat_router,
    ):
        app.include_router(r)
    return app


app = create_app()
