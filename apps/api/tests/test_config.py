from __future__ import annotations

from app.config import Settings


def test_production_refuses_unsafe_defaults():
    s = Settings(
        environment="production",
        jwt_secret="dev-only-change-me",
        database_url="sqlite+aiosqlite:///x.db",
        redis_url="",
        llm_provider="fake",
        token_encryption_key="",
    )
    problems = " | ".join(s.production_problems())
    for word in ("JWT_SECRET", "TOKEN_ENCRYPTION_KEY", "Postgres", "REDIS_URL", "LLM_PROVIDER"):
        assert word in problems


def test_production_ok_when_configured():
    s = Settings(
        environment="production",
        jwt_secret="x" * 40,
        token_encryption_key="k",
        database_url="postgresql+asyncpg://u:p@h/db",
        redis_url="redis://h:6379/0",
        llm_provider="anthropic",
    )
    assert s.production_problems() == []
    assert Settings(environment="development").production_problems() == []


def test_job_board_list_parsing():
    s = Settings(job_boards=" greenhouse:stripe, lever:netflix ,bad, ashby:openai")
    assert s.job_board_list == [("greenhouse", "stripe"), ("lever", "netflix"), ("ashby", "openai")]


def test_database_url_gets_async_driver():
    assert Settings(database_url="postgres://u:p@h:5432/db").database_url == "postgresql+asyncpg://u:p@h:5432/db"
    assert Settings(database_url="postgresql://u:p@h/db").database_url == "postgresql+asyncpg://u:p@h/db"
    assert Settings(database_url="postgresql+asyncpg://u:p@h/db").database_url == "postgresql+asyncpg://u:p@h/db"
