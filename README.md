# Life Easy — Personal AI Job Assistant

A cloud-deployable personal AI assistant for job discovery, job matching, recruiter research, application tracking, and approval-based email drafting/sending.

## Product goals

- Conversational command interface for job-search tasks.
- Search permitted job sources and company career pages; never scrape LinkedIn pages or bypass access controls.
- Match opportunities against a user's verified profile and resume.
- Find only publicly listed recruiter contact channels and cite their source.
- Generate personalized Gmail drafts and require explicit approval before sending.
- Track opportunities, applications, contacts, and conversation memory.
- Keep provider integrations behind adapters so the app can move between hosting providers.

## Deployment target

- **Web:** Next.js on Vercel.
- **API and workers:** FastAPI on Render.
- **Database:** Managed PostgreSQL with pgvector.
- **Queue/cache:** Redis-compatible managed service.
- **Files:** Object storage for uploaded resumes.
- **Messaging:** Telegram Bot API for supported two-way bot conversations; WhatsApp personal accounts do not expose an officially supported general-purpose bot API. WhatsApp Business Platform can be added through an approved provider, subject to Meta onboarding, templates, policy, and possible fees.

Free tiers have limits and can sleep, expire, or change. Do not use ephemeral/free database instances for important user data.

## Repository layout

```text
apps/
  api/       FastAPI service
  web/       Next.js dashboard
packages/
  contracts/ Shared API schemas and types
infra/
  docker/    Local development services
docs/
  architecture.md
  security.md
.github/
  workflows/ CI
```

## Initial status

This repository is the project foundation. Integrations that require OAuth credentials, platform approval, or paid hosting must be configured by the repository owner. Never commit secrets.

## Quick start

See the app-specific READMEs and `.env.example` files. Use Docker Compose for local development, then deploy the web app and API separately.

## Security principles

- OAuth tokens encrypted at rest.
- Secrets only in environment variables or hosting secret stores.
- Per-user data isolation and authorization on every API route.
- Explicit confirmation for external actions such as sending an email.
- Audit log for approvals and external actions.
- Rate limits, retries, idempotency, and provider quotas.
- Resume contents and recruiter data are private user data; do not expose them in public logs.

## License

Proprietary personal project. Add a license only when the owner decides how the code may be reused.
