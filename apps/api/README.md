# Life Easy API

FastAPI service intended for Render. Python 3.12+.

## Local setup

```bash
python -m venv .venv
# Activate the virtual environment, then:
pip install -r requirements.txt
cp .env.example .env
```

Set `DATABASE_URL` and a cryptographically random `JWT_SECRET` of at least 32 characters. Create a PostgreSQL database, then apply migrations:

```bash
python -m app.migrate
uvicorn app.main:app --reload
```

## Implemented API foundation

- `GET /health` — service health.
- `POST /api/v1/auth/register` — email/password registration.
- `POST /api/v1/auth/login` — login and short-lived bearer token.
- `GET /api/v1/auth/me` — current authenticated user.
- `GET/PUT /api/v1/profile` — user-scoped career profile.
- `POST /api/v1/jobs/search` — search jobs already indexed in PostgreSQL and compute explainable baseline matching.
- `POST /api/v1/jobs/{id}/save`, `GET /api/v1/jobs/saved` — user-scoped saved jobs.
- `POST/GET /api/v1/approvals` — create and list exact-message approval records.
- `POST /api/v1/approvals/{id}/confirm` — approve or cancel the exact content hash.

All authenticated endpoints use bearer JWTs and scope records to the authenticated user. The API does not send approved messages yet: the execution worker and Gmail/LinkedIn/WhatsApp send adapters must be implemented before external actions can run.

## Not yet production-ready

Email/phone OTP verification, OAuth login, password reset, secure HttpOnly cookie sessions, resume object storage, live job-source ingestion adapters, AI orchestration, WhatsApp sender binding and auto-replies, Gmail OAuth, LinkedIn authorized actions, background workers, rate limiting, observability, and end-to-end tests remain to be completed.

Never commit `.env` or provider credentials.
