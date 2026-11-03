"""Application settings.

Every environment variable the API, worker and tests read is declared here, so
there is exactly one place to look. Values come from the process environment or
a local `.env` file (never committed). Provider credentials stay empty until the
owner configures them in the hosting secret store.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # --- core -----------------------------------------------------------------
    app_name: str = "Life Easy API"
    environment: Literal["development", "test", "production"] = "development"
    frontend_origin: str = "http://localhost:3000"
    public_api_url: str = "http://localhost:8000"
    log_level: str = "INFO"

    # --- storage --------------------------------------------------------------
    # SQLite is for local development and tests only; production needs Postgres + pgvector.
    database_url: str = "sqlite+aiosqlite:///./life_easy.db"
    redis_url: str = ""  # empty -> inline task runner (no queue) and in-memory rate limits
    embedding_dim: int = 1024  # must match the embedding provider (Voyage voyage-3 = 1024)

    # Object storage for resumes/documents. S3-compatible; empty bucket -> local disk folder.
    storage_bucket: str = ""
    storage_endpoint_url: str = ""
    storage_region: str = "auto"
    storage_access_key_id: str = ""
    storage_secret_access_key: str = ""
    storage_local_dir: str = "./storage"

    # --- security -------------------------------------------------------------
    jwt_secret: str = Field(default="dev-only-change-me", min_length=16)
    jwt_issuer: str = "life-easy"
    access_token_minutes: int = 60
    refresh_token_days: int = 30
    # Fernet key (urlsafe base64, 32 bytes) for OAuth tokens at rest. Required in production.
    token_encryption_key: str = ""
    rate_limit_per_minute: int = 60

    # --- AI -------------------------------------------------------------------
    llm_provider: Literal["anthropic", "fake"] = "fake"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-5"
    embedding_provider: Literal["voyage", "hash"] = "hash"
    voyage_api_key: str = ""
    voyage_model: str = "voyage-3"
    max_llm_calls_per_user_per_day: int = 300

    # --- messaging channels ---------------------------------------------------
    whatsapp_webhook_verify_token: str = ""
    whatsapp_app_secret: str = ""
    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_graph_api_version: str = "v21.0"

    telegram_bot_token: str = ""
    telegram_webhook_secret: str = ""  # sent back by Telegram in X-Telegram-Bot-Api-Secret-Token

    # --- email providers ------------------------------------------------------
    google_client_id: str = ""
    google_client_secret: str = ""
    microsoft_client_id: str = ""
    microsoft_client_secret: str = ""
    microsoft_tenant: str = "common"
    linkedin_client_id: str = ""
    linkedin_client_secret: str = ""

    # --- job sources ----------------------------------------------------------
    adzuna_app_id: str = ""
    adzuna_app_key: str = ""
    adzuna_country: str = "in"
    # Comma-separated board tokens, e.g. "greenhouse:stripe,lever:netflix,ashby:openai"
    job_boards: str = ""

    # --- approvals ------------------------------------------------------------
    approval_ttl_hours: int = 48

    @field_validator("database_url")
    @classmethod
    def _async_driver(cls, value: str) -> str:
        """Hosting providers hand out postgres:// or postgresql:// URLs; the app needs the asyncpg driver."""
        for prefix in ("postgres://", "postgresql://"):
            if value.startswith(prefix):
                return "postgresql+asyncpg://" + value[len(prefix) :]
        return value

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def job_board_list(self) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        for item in self.job_boards.split(","):
            item = item.strip()
            if not item or ":" not in item:
                continue
            provider, token = item.split(":", 1)
            out.append((provider.strip().lower(), token.strip()))
        return out

    def production_problems(self) -> list[str]:
        """Settings that are fine for a laptop but unsafe in production. Empty list = OK."""
        if not self.is_production:
            return []
        problems = []
        if self.jwt_secret == "dev-only-change-me" or len(self.jwt_secret) < 32:
            problems.append("JWT_SECRET must be a random value of at least 32 characters")
        if not self.token_encryption_key:
            problems.append("TOKEN_ENCRYPTION_KEY is required (Fernet key) to encrypt OAuth tokens and app passwords")
        if self.is_sqlite:
            problems.append("DATABASE_URL must point at Postgres (SQLite is for development only)")
        if not self.redis_url:
            problems.append("REDIS_URL is required so background work runs in the worker, not inside requests")
        if self.llm_provider == "fake":
            problems.append("LLM_PROVIDER=fake gives placeholder answers; set LLM_PROVIDER=anthropic and ANTHROPIC_API_KEY")
        return problems


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    """Tests change environment variables and need a fresh Settings object."""
    get_settings.cache_clear()
