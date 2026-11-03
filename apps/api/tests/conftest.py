"""Test setup: SQLite file DB, fake LLM/embeddings, local storage, inline task runner, recording channel adapters.

Environment variables are set BEFORE the app is imported, because settings are read at import time.
"""

from __future__ import annotations

import os
import pathlib
import tempfile
from typing import Any

TMP = pathlib.Path(tempfile.mkdtemp(prefix="lifeeasy-test-"))
os.environ.update(
    {
        "ENVIRONMENT": "test",
        "DATABASE_URL": f"sqlite+aiosqlite:///{(TMP / 'test.db').as_posix()}",
        "JWT_SECRET": "test-secret-key-at-least-16-chars",
        "TOKEN_ENCRYPTION_KEY": "",
        "STORAGE_LOCAL_DIR": str(TMP / "storage"),
        "STORAGE_BUCKET": "",
        "LLM_PROVIDER": "fake",
        "EMBEDDING_PROVIDER": "hash",
        "EMBEDDING_DIM": "64",
        "REDIS_URL": "",
        "FRONTEND_ORIGIN": "http://localhost:3000",
        "PUBLIC_API_URL": "http://test",
        "WHATSAPP_WEBHOOK_VERIFY_TOKEN": "verify-token",
        "WHATSAPP_APP_SECRET": "app-secret",
        "WHATSAPP_ACCESS_TOKEN": "wa-token",
        "WHATSAPP_PHONE_NUMBER_ID": "12345",
        "WHATSAPP_GRAPH_API_VERSION": "v21.0",
        "TELEGRAM_BOT_TOKEN": "tg-token",
        "TELEGRAM_WEBHOOK_SECRET": "tg-secret",
        "JOB_BOARDS": "",
        "ADZUNA_APP_ID": "",
        "ADZUNA_APP_KEY": "",
        "MAX_LLM_CALLS_PER_USER_PER_DAY": "1000",
    }
)

from app.config import reset_settings_cache  # noqa: E402

reset_settings_cache()

import httpx  # noqa: E402
import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from app.ai.embeddings import set_embeddings  # noqa: E402
from app.ai.llm import FakeLLM, set_llm  # noqa: E402
from app.channels.base import Button, ChannelAdapter, InboundMessage  # noqa: E402
from app.channels.pipeline import set_adapter  # noqa: E402
from app.channels.telegram import TelegramAdapter  # noqa: E402
from app.channels.whatsapp import WhatsAppAdapter  # noqa: E402
from app.db import models as m  # noqa: E402
from app.db.session import dispose_engine, get_engine, get_session_factory  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402
from app.resumes.storage import set_storage  # noqa: E402
from app.security.crypto import reset_secret_box  # noqa: E402
from app.security.ratelimit import reset_limiter  # noqa: E402
from app.tasks.runner import clear_inline_calls, set_inline_execution_for_tests  # noqa: E402


class RecordingAdapter(ChannelAdapter):
    """Stands in for WhatsApp/Telegram delivery: parses like the real one, records what would be sent."""

    def __init__(self, name: str) -> None:
        self.name = name
        self._real: ChannelAdapter = WhatsAppAdapter() if name == "whatsapp" else TelegramAdapter()
        self.sent: list[dict[str, Any]] = []

    def configured(self) -> bool:
        return True

    def parse(self, payload: dict[str, Any]) -> list[InboundMessage]:
        return self._real.parse(payload)

    async def send_text(self, external_id: str, text: str) -> None:
        self.sent.append({"to": external_id, "text": text, "buttons": []})

    async def send_buttons(self, external_id: str, text: str, buttons: list[Button]) -> None:
        self.sent.append({"to": external_id, "text": text, "buttons": [b.id for b in buttons]})

    def texts(self) -> list[str]:
        return [s["text"] for s in self.sent]


@pytest_asyncio.fixture(autouse=True)
async def _fresh_state():
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(m.Base.metadata.drop_all)
        await conn.run_sync(m.Base.metadata.create_all)
    reset_limiter()
    reset_secret_box()
    set_llm(None)
    set_embeddings(None)
    set_storage(None)
    clear_inline_calls()
    set_inline_execution_for_tests(False)
    yield
    await dispose_engine()


@pytest.fixture
def whatsapp():
    adapter = RecordingAdapter("whatsapp")
    set_adapter("whatsapp", adapter)
    yield adapter
    set_adapter("whatsapp", WhatsAppAdapter())


@pytest.fixture
def telegram():
    adapter = RecordingAdapter("telegram")
    set_adapter("telegram", adapter)
    yield adapter
    set_adapter("telegram", TelegramAdapter())


@pytest.fixture
def inline_tasks():
    """Background tasks run inside the request, like a worker would, so flows can be checked end to end."""
    set_inline_execution_for_tests(True)
    yield
    set_inline_execution_for_tests(False)


@pytest.fixture
def fake_llm() -> FakeLLM:
    llm = FakeLLM()
    set_llm(llm)
    return llm


@pytest_asyncio.fixture
async def client():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=fastapi_app), base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def session():
    async with get_session_factory()() as s:
        yield s


async def register(
    client: httpx.AsyncClient, email: str = "amir@example.com", password: str = "correct horse battery"
) -> dict[str, str]:
    resp = await client.post("/api/v1/auth/register", json={"email": email, "password": password, "display_name": "Amir"})
    assert resp.status_code == 201, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest_asyncio.fixture
async def auth(client) -> dict[str, str]:
    return await register(client)


async def make_user(session, email: str = "u@example.com", **profile: Any) -> m.User:  # noqa: ANN001
    user = m.User(email=email, password_hash="x", display_name="Test User")
    session.add(user)
    await session.flush()
    session.add(m.Profile(user_id=user.id, **profile))
    await session.flush()
    return user
