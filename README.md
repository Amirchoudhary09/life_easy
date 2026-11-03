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

Not built yet: billing / paid plans; the additional web screens listed in [Launch readiness and ownership](#launch-readiness-and-ownership); safer HttpOnly-cookie + CSRF browser authentication (current refresh-token handling needs a security review); Postgres row-level security (isolation is enforced in application code and covered by tests); error tracking (Sentry); and submitting job applications on an ATS for you (you apply via the posting link; Life Easy tracks it).

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


## Launch readiness and ownership

This section separates work that belongs to the **developer** from information, accounts, approvals, and credentials that must be supplied by the **author / product owner**. Never commit real credentials, personal phone numbers, OAuth secrets, access tokens, or production connection strings. Enter secrets only in the hosting provider's secret manager.

### Status labels

- **[DEVELOPER REQUIRED]** — implementation, UI, integration, security, tests, documentation, or deployment engineering.
- **[AUTHOR REQUIRED]** — the product owner must provide an account, business detail, phone number, consent, verification, permission, or credential.
- **[BOTH REQUIRED]** — the developer configures/tests the integration and the author supplies access or completes provider-side approval.
- **[OPTIONAL]** — only needed if the corresponding provider or capability is enabled.

### A. Product work still required

| Status | Item | Owner | Acceptance criteria |
|---|---|---|---|
| [ ] | Safer browser authentication: HttpOnly, Secure, SameSite cookies, CSRF protection, refresh rotation and logout behavior | [DEVELOPER REQUIRED] | No refresh token in browser localStorage; cookie and CSRF tests pass; OAuth and API flows continue to work. |
| [ ] | Email web screen: inbox, message detail, compose, drafts, sent status and approval preview | [DEVELOPER REQUIRED] | Uses existing email APIs; sending is impossible without approval of the exact recipient and content. |
| [ ] | LinkedIn web screen: post/message drafts, preview, approval and publish status | [DEVELOPER REQUIRED] | Uses supported official LinkedIn APIs only; messages that cannot be sent through an official API are clearly presented as copy-ready drafts. |
| [ ] | Application event timeline screen | [DEVELOPER REQUIRED] | Shows the events returned by `GET /applications/{id}/events` in chronological order. |
| [ ] | Edit interview screen | [DEVELOPER REQUIRED] | Supports the existing interview update API, validation and timezone-safe date handling. |
| [ ] | Manual follow-up creation screen | [DEVELOPER REQUIRED] | Lets a user create, view and update follow-ups against their own application. |
| [ ] | Logout from all devices in account/security settings | [DEVELOPER REQUIRED] | Calls `POST /auth/logout-all`, invalidates sessions and reports the result. |
| [ ] | Billing and subscription plans | [DEVELOPER REQUIRED] | Defer until launch scope and pricing are decided; implement payment-provider webhooks, entitlements, cancellation and billing tests before charging users. |
| [ ] | Postgres row-level security, error monitoring, backup/restore, dependency update policy, message-retention policy and WhatsApp webhook timestamp/replay hardening | [DEVELOPER REQUIRED] | Close the open items in [docs/security.md](docs/security.md) and document operational evidence. |
| [ ] | Full integration / end-to-end test | [BOTH REQUIRED] | Link a real Telegram account, chat with the agent, create an email draft, approve the exact preview, send it, and verify the provider result and audit event. Repeat relevant checks for WhatsApp and email OAuth before public launch. |

### B. Author / account-owner information and provider setup

The application does **not** need the author's personal mobile number hard-coded in source code. A user enters or links their own channel identity inside the application. The phone number below is the **business sender number** used by the platform's WhatsApp Business integration.

| Status | Required input or account | Owner | Where it is used / notes |
|---|---|---|---|
| [ ] | Production owner email address and initial admin designation | [AUTHOR REQUIRED] | Supply the email address to the developer through a secure channel. Do not put a password or admin token in README. Configure the approved admin allowlist only after the account exists and is verified, if the current deployment uses one. |
| [ ] | Meta Business account, WhatsApp Business Account, approved business sender mobile number, Phone Number ID, access token, App Secret and webhook verification token | [AUTHOR REQUIRED] | Needed only to enable WhatsApp Business messaging. The sender number must be registered with Meta; end users link their own WhatsApp account through the in-app one-time linking flow. |
| [ ] | Telegram bot created through BotFather and bot token | [AUTHOR REQUIRED] | Needed to enable Telegram. The developer then configures the webhook URL and secret. |
| [ ] | Google Cloud project, OAuth consent screen, web OAuth client ID/secret and authorized redirect URI | [AUTHOR REQUIRED] | Needed for Gmail. Gmail restricted scopes may require Google verification and security assessment before public availability; test-user access may be used during development. |
| [ ] | Microsoft Entra tenant/app registration, client ID/secret and delegated mail permissions | [AUTHOR REQUIRED] | Needed for Outlook / Microsoft 365 OAuth. |
| [ ] | LinkedIn developer app, client ID/secret and approved products/scopes | [AUTHOR REQUIRED] | Needed for LinkedIn sign-in and post publishing. API access is subject to LinkedIn approval; do not assume member messaging is available. |
| [ ] | Adzuna application ID and key | [AUTHOR REQUIRED] | Optional job source; public company career boards work without these credentials. Set country to `in` for India. |
| [ ] | Anthropic API key and selected model | [AUTHOR REQUIRED] | Required for real AI responses when `LLM_PROVIDER=anthropic`; fake mode is only for local/test use. |
| [ ] | Voyage API key and embedding model | [AUTHOR REQUIRED] | Optional. Hash embeddings can be used as a basic fallback; if using Voyage, set `EMBEDDING_DIM` consistently before the first production migration. |
| [ ] | Private object-storage account/bucket and access credentials (S3-compatible, e.g. R2/S3/B2) | [AUTHOR REQUIRED] | Strongly recommended/required for durable resume storage in production. Local container storage is not durable across redeploys. |
| [ ] | Production domain and DNS access | [AUTHOR REQUIRED] | Needed if using a custom web/API domain and provider OAuth redirect URLs. |
| [ ] | Provider-side verification, app review, webhook subscription and permission approval | [AUTHOR REQUIRED] | Complete the relevant provider's review steps and share confirmation with the developer; never send secret values in public issues or README. |

### C. Developer configuration and deployment checklist

| Status | Task | Owner | Notes |
|---|---|---|---|
| [ ] | Generate strong production `JWT_SECRET` and Fernet `TOKEN_ENCRYPTION_KEY` | [DEVELOPER REQUIRED] | Generate independently for production; store only in Render secret settings. Never reuse development values. |
| [ ] | Configure production PostgreSQL with pgvector and run `alembic upgrade head` | [BOTH REQUIRED] | Author provides hosting/project access; developer configures connection, verifies extensions and migration state. |
| [ ] | Configure Redis and deploy API plus background worker | [BOTH REQUIRED] | Required for scheduled automations and reliable queued work. Confirm worker health and cron execution. |
| [ ] | Configure all applicable environment variables from `apps/api/.env.example` in the host secret manager | [BOTH REQUIRED] | Do not set unused provider credentials. Ensure API and worker receive the same required configuration. |
| [ ] | Configure Vercel `NEXT_PUBLIC_API_BASE_URL` and API `FRONTEND_ORIGIN` / `PUBLIC_API_URL` | [BOTH REQUIRED] | Verify CORS, HTTPS and OAuth callback URLs against the actual production domains. |
| [ ] | Configure provider webhooks | [BOTH REQUIRED] | WhatsApp webhook: `/api/v1/webhooks/whatsapp`; Telegram webhook: use the authenticated setup endpoint after deployment. Verify signatures/secrets and delivery. |
| [ ] | Configure private object storage and test resume upload/download/deletion | [BOTH REQUIRED] | Confirm objects are private and user ownership is enforced. |
| [ ] | Run CI, migration checks, API tests, web typecheck/build and smoke tests against production | [DEVELOPER REQUIRED] | Record deployment SHA and test evidence. Do not mark production ready based on a successful frontend deployment alone. |
| [ ] | Configure backups and perform a restore drill | [BOTH REQUIRED] | Confirm retention, restore point and recovery procedure with the database provider. |
| [ ] | Verify account isolation, approval gates, logout-all, data export/deletion and audit trail with two test users | [DEVELOPER REQUIRED] | Never use real user resumes or send real external messages without explicit test approval. |

### D. Environment-variable ownership map

Use [apps/api/.env.example](apps/api/.env.example) as the canonical variable list. The following map explains who supplies the underlying value; the developer still wires each value into the deployment.

| Environment variable(s) | Value supplied by | Required? |
|---|---|---|
| `JWT_SECRET`, `TOKEN_ENCRYPTION_KEY` | [DEVELOPER REQUIRED] generate; [AUTHOR REQUIRED] authorize/store in hosting account | Production mandatory |
| `DATABASE_URL`, `REDIS_URL` | [BOTH REQUIRED] hosting account + developer configuration | Production mandatory |
| `ANTHROPIC_API_KEY` | [AUTHOR REQUIRED] | Required for Anthropic AI |
| `VOYAGE_API_KEY` | [AUTHOR REQUIRED] | Optional if hash embeddings are accepted |
| `WHATSAPP_WEBHOOK_VERIFY_TOKEN`, `WHATSAPP_APP_SECRET`, `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID` | [AUTHOR REQUIRED] obtain from Meta; [DEVELOPER REQUIRED] configure and verify | Required only for WhatsApp |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET` | [AUTHOR REQUIRED] create bot and secret; [DEVELOPER REQUIRED] register webhook | Required only for Telegram |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | [AUTHOR REQUIRED] create OAuth app; [DEVELOPER REQUIRED] configure callback/scopes | Required only for Gmail OAuth |
| `MICROSOFT_CLIENT_ID`, `MICROSOFT_CLIENT_SECRET`, `MICROSOFT_TENANT` | [AUTHOR REQUIRED] create Entra app; [DEVELOPER REQUIRED] configure callback/scopes | Required only for Outlook OAuth |
| `LINKEDIN_CLIENT_ID`, `LINKEDIN_CLIENT_SECRET` | [AUTHOR REQUIRED] create LinkedIn app and obtain permissions; [DEVELOPER REQUIRED] configure integration | Required only for LinkedIn |
| `ADZUNA_APP_ID`, `ADZUNA_APP_KEY`, `ADZUNA_COUNTRY` | [AUTHOR REQUIRED] obtain app credentials; [DEVELOPER REQUIRED] configure | Optional source |
| `STORAGE_BUCKET`, `STORAGE_ENDPOINT_URL`, `STORAGE_REGION`, `STORAGE_ACCESS_KEY_ID`, `STORAGE_SECRET_ACCESS_KEY` | [AUTHOR REQUIRED] create private bucket/credentials; [DEVELOPER REQUIRED] configure and test | Production resume storage |
| `FRONTEND_ORIGIN`, `PUBLIC_API_URL`, `NEXT_PUBLIC_API_BASE_URL` | [BOTH REQUIRED] domain owner provides domain; developer sets matching URLs | Production mandatory |
| `JOB_BOARDS` | [DEVELOPER REQUIRED] configure desired public company board slugs | Optional; default examples are included |
| `LLM_PROVIDER`, `ANTHROPIC_MODEL`, `EMBEDDING_PROVIDER`, `VOYAGE_MODEL`, `EMBEDDING_DIM`, `MAX_LLM_CALLS_PER_USER_PER_DAY` | [DEVELOPER REQUIRED] choose safe settings; [AUTHOR REQUIRED] approve cost/usage policy | Configuration required |

### E. Phone number and personal profile requirements

- **[AUTHOR REQUIRED]** Each user supplies their own phone number only when linking a phone-based channel or when the product's profile flow explicitly asks for it. It must not be hard-coded or stored in the repository.
- **[AUTHOR REQUIRED]** The platform owner supplies a separate Meta WhatsApp Business sender number and its Meta Phone Number ID to enable outbound WhatsApp integration.
- **[DEVELOPER REQUIRED]** Confirm whether the profile currently collects a phone number, validate it in international E.164 format where needed, explain why it is collected, and provide consent, update and deletion behavior. Do not make a phone number mandatory for users who only want web/email/Telegram features.
- **[DEVELOPER REQUIRED]** Ensure phone numbers and channel identifiers are encrypted or access-controlled as appropriate and always redacted from logs.

### F. Launch decision

Do not announce a public launch until all production-mandatory items above are checked, the provider permissions are approved, database migrations and backups are verified, and the end-to-end approval workflow has passed. Features that depend on an unconfigured provider must be shown as unavailable/not connected in the UI rather than appearing operational.

## License

Proprietary personal project. Add a license only when the owner decides how the code may be reused.
