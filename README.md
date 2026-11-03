# Life Easy — Career-first Personal AI Assistant

Life Easy is a multi-user AI assistant with **job hunting as its primary product** and career productivity (email, LinkedIn, resumes, interview prep) as supporting capabilities. You talk to it from the web dashboard, WhatsApp or Telegram. It searches, matches and drafts on its own, but **nothing is sent to another person or published until you approve the exact message**.

## What works now

| Area | What it does |
|---|---|
| Accounts | Email + password sign-up (Argon2id), short-lived access tokens + rotating refresh tokens, profile & job preferences, data export (JSON), account deletion with full purge |
| Resumes | Upload PDF / DOCX / TXT / MD (≤ 5 MB, private storage), text extraction, AI parsing into skills / experience, primary resume, per-job tailored versions with an ATS keyword report |
| Job discovery | Public company boards: **Greenhouse, Lever, Ashby, Workable, SmartRecruiters** (no key needed) + **Adzuna** search API (free key, covers India). De-duplication, change detection, stale-job deactivation, source links + fetch times kept |
| Matching | Embedding shortlist → rule score (title, skills, location, recency, employment type, excluded companies) → AI explanation (strengths / gaps) for the top results. Save / skip / “I applied” |
| Tracker | Applications with a status timeline, interviews, follow-ups, weekly stats |
| Approvals | Every outbound action becomes a preview (channel, from, to/cc, subject, full body, attachments). Approval is bound to a SHA-256 content hash; any edit creates a new preview; each approval executes once and is audited |
| Email | Gmail (OAuth), Outlook / Microsoft 365 (OAuth), **any mailbox via IMAP/SMTP app password** (Yahoo, Zoho, iCloud, custom domains). AI drafts; sending only through approvals; inbox read for reply detection |
| LinkedIn | AI drafts for posts, connection notes, recruiter messages. Posts publish through the official Posts API after approval when LinkedIn is connected; messages are handed back for you to paste (LinkedIn has no member-messaging API). No scraping |
| Chat agent | One agent with tools (search jobs, matches, tracker, profile, drafts, tailoring, interview prep, public-contact research with evidence, memory). Third-party text is wrapped as untrusted data (prompt-injection guard). Per-user daily AI call limit |
| WhatsApp & Telegram | Official WhatsApp Cloud API + Telegram Bot API webhooks (signature / secret checked), account linking with a one-time code, de-duplicated deliveries, Approve / Reject buttons, `STOP` to unlink |
| Automations | Daily job digest at your local hour (Save / Skip / Tailor buttons), follow-up drafts after 7 quiet days, inbox watching (interview invites, rejections, offers update the tracker), interview prep pack the day before, weekly report, approval expiry, 90-day contact retention |
| Ops | Postgres + pgvector schema via Alembic, Redis queue + cron worker (arq), structured logs with request IDs and secret redaction, rate limits, Docker images, docker-compose, Render blueprint, CI (lint, 69 tests, migrations on real Postgres, web build) |

Not built yet: billing / plan limits beyond the daily AI cap, Postgres row-level security (isolation is enforced in code and covered by tests), error tracking (Sentry), submitting job applications on an ATS for you (you apply via the posting link; Life Easy tracks it).

## Repository layout

```text
apps/
  api/              FastAPI service + arq worker (Python 3.12)
    app/            auth, me, resumes, jobs (+ sources), applications, approvals,
                    email, linkedin, channels, agent, chat, automations, tasks
    alembic/        database migrations
    tests/          pytest suite (SQLite, fake AI, recorded channel adapters)
  web/              Next.js 15 dashboard (App Router, TypeScript)
database/schema.sql generated Postgres DDL (reference only; apply with Alembic)
infra/render.yaml   Render blueprint (API, worker, Postgres, Redis)
docs/               architecture, security checklist, provider setup
docker-compose.yml  local full stack
```

## Run it locally

### Option A: everything in Docker

```bash
cp apps/api/.env.example apps/api/.env      # fill in only what you want to try
docker compose up --build
```

Dashboard: http://localhost:3000 · API docs: http://localhost:8000/docs. The API container runs `alembic upgrade head` on start; the worker runs the queue and all scheduled automations.

### Option B: no Docker (SQLite, no Redis)

```bash
# API (terminal 1)
cd apps/api
python -m venv .venv && .venv/Scripts/activate        # macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env                                   # defaults: SQLite, fake AI, tasks run inline
uvicorn app.main:app --reload --port 8000

# Web (terminal 2)
cd apps/web
npm ci
echo NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 > .env.local
npm run dev
```

Without `REDIS_URL`, background tasks run inside the request (fine for trying it out) and scheduled automations don't run. Trigger one by hand from `apps/api`, for example:

```bash
python -c "import asyncio; from app.automations.digest import run_daily_digest; print(asyncio.run(run_daily_digest()))"
```

With `LLM_PROVIDER=fake` the assistant answers with placeholders. Set `LLM_PROVIDER=anthropic` and `ANTHROPIC_API_KEY` for real answers, drafts and matching explanations.

### Tests and checks

```bash
cd apps/api && pytest -q && ruff check app tests && ruff format --check app tests
cd apps/web && npm run typecheck && npm run build
```

## Configuration and providers

Every setting is listed with a comment in [apps/api/.env.example](apps/api/.env.example). In production, set them in the hosting secret store. The API and worker **refuse to start in production** with a default `JWT_SECRET`, without `TOKEN_ENCRYPTION_KEY`, on SQLite, without Redis, or with the fake AI.

| Provider | What to create | Settings |
|---|---|---|
| Anthropic (AI) | API key at console.anthropic.com | `LLM_PROVIDER=anthropic`, `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` |
| Voyage (embeddings) | API key at voyageai.com | `EMBEDDING_PROVIDER=voyage`, `VOYAGE_API_KEY`, `EMBEDDING_DIM=1024` (set before the first migration) |
| Job boards | Nothing; find a company's board slug in its careers URL (e.g. `boards.greenhouse.io/stripe`) | `JOB_BOARDS=greenhouse:stripe,lever:palantir,ashby:openai,workable:<sub>,smartrecruiters:<id>` |
| Adzuna | Free app id + key at developer.adzuna.com | `ADZUNA_APP_ID`, `ADZUNA_APP_KEY`, `ADZUNA_COUNTRY=in` |
| WhatsApp | Meta app + WhatsApp Business number, system-user token. Webhook URL `https://<api>/api/v1/webhooks/whatsapp`, field `messages`. See [docs/whatsapp-setup.md](docs/whatsapp-setup.md) | `WHATSAPP_*` |
| Telegram | Bot from @BotFather. After deploying, call `POST /api/v1/channels/telegram/set-webhook` once (logged in) | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET` |
| Gmail | Google Cloud OAuth client (web). Redirect URI `https://<api>/api/v1/connections/oauth/google/callback`. Scopes `gmail.send` + `gmail.readonly` are *restricted*: public launch needs Google verification and a yearly security assessment; test users work before that | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` |
| Outlook / M365 | Entra ID app registration, redirect URI `https://<api>/api/v1/connections/oauth/microsoft/callback`, delegated `Mail.Send`, `Mail.Read`, `User.Read`, `offline_access` | `MICROSOFT_CLIENT_ID`, `MICROSOFT_CLIENT_SECRET`, `MICROSOFT_TENANT=common` |
| Other mail | Nothing; users add IMAP/SMTP with an app password in Settings | — |
| LinkedIn | LinkedIn developer app with “Sign In with LinkedIn (OpenID)” + “Share on LinkedIn” (`w_member_social`). Redirect URI `https://<api>/api/v1/connections/oauth/linkedin/callback` | `LINKEDIN_CLIENT_ID`, `LINKEDIN_CLIENT_SECRET` |
| Object storage | Private S3-compatible bucket (Cloudflare R2, S3, B2) | `STORAGE_*` |

## Deploy

- **API + worker + Postgres + Redis:** Render → New → Blueprint → `infra/render.yaml`. Fill the `sync: false` values. The API runs migrations on start. Free plans sleep and free Postgres expires; use paid plans for real users.
- **Web:** Vercel, project root `apps/web`, set `NEXT_PUBLIC_API_BASE_URL` to the API URL. Set the API's `FRONTEND_ORIGIN` to the Vercel URL.

## Security principles

Per-user isolation on every route and query · OAuth tokens and app passwords encrypted at rest (Fernet) · secrets only in the hosting secret store · explicit per-message approval before any external action · insert-only audit trail · rate limits and idempotency · no message bodies, resumes or tokens in logs · export, disconnect and deletion for every user. Checklist and status: [docs/security.md](docs/security.md).

## Mandatory send approval

Life Easy must show the exact destination, channel, complete message, and attachments and obtain the user's explicit final approval before sending any message to another person or publishing to an external audience. This applies separately to every email, LinkedIn message/post, recruiter outreach, and other outbound communication. Editing the recipient or content invalidates the approval. Normal assistant replies to the user in their active chat do not need an extra confirmation.

## License

Proprietary personal project. Add a license only when the owner decides how the code may be reused.
