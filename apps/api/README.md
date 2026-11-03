# Life Easy API

FastAPI service + arq worker. Python 3.12.

```bash
python -m venv .venv && .venv/Scripts/activate      # macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
uvicorn app.main:app --reload                       # http://localhost:8000/docs
arq app.worker.WorkerSettings                       # worker + scheduled automations (needs REDIS_URL)
```

- SQLite (`DATABASE_URL=sqlite+aiosqlite:///./life_easy.db`): tables are created on start. For development only.
- Postgres: `alembic upgrade head` (the Docker image does this on start). New migration after a model change: `alembic revision --autogenerate -m "..."`, then review it.
- No `REDIS_URL`: background tasks run inline inside the request, and cron automations don't run.

Main routes (all under `/api/v1`, bearer token except webhooks and OAuth callbacks):

| Prefix | Purpose |
|---|---|
| `auth/*` | register, login, refresh, logout, logout-all, me |
| `me/*` | profile + preferences, export, delete account |
| `resumes/*` | upload, list, download, primary, delete, tailor |
| `jobs`, `jobs/{id}`, `jobs/ingest`, `jobs/sources` | search and fetch jobs |
| `matches`, `matches/refresh`, `matches/{job_id}` | ranked matches, save / skip / applied |
| `applications/*`, `interviews`, `follow-ups` | tracker |
| `approvals/*` | list, approve (needs `content_hash`), reject, edit |
| `email/*`, `connections/oauth/{provider}/*` | mail connections (Google, Microsoft, LinkedIn OAuth; IMAP), drafts, send (creates approval), inbox |
| `linkedin/*` | post and message drafts, publish / message (create approvals) |
| `chat/*` | web chat with the agent, history, notifications feed |
| `channels/*`, `webhooks/whatsapp`, `webhooks/telegram` | link codes, linked chats, provider webhooks |

Tests: `pytest -q` (SQLite in a temp folder, fake AI, recording channel adapters; no network). Lint: `ruff check app tests && ruff format --check app tests`.
