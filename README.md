# Life Easy — Career-first Personal AI Assistant

Life Easy is a multi-user, cloud-hosted AI assistant with **job hunting as its primary product** and career-related productivity as supporting capabilities.

## Product direction

**Primary: AI job hunting**
- Discover relevant jobs from permitted public job boards, APIs, and company career pages.
- Match openings against each user's resume, skills, experience, location, and salary preferences.
- Explain match quality and preserve job source links and retrieval timestamps.
- Research publicly listed recruiter contacts with source evidence; never guess private contact details.
- Draft tailored applications and recruiter outreach.
- Track saved roles, applications, interviews, follow-ups, and outcomes.

**Supporting: career-focused assistant**
- Draft and send career-related emails through each user's own connected email account, only after explicit approval.
- Prepare LinkedIn posts, recruiter messages, connection notes, and profile copy.
- Publish or perform LinkedIn actions only through supported, authorized integrations and user approval; never scrape pages or automate session-cookie/browser access.
- Help with resumes, cover letters, interview preparation, career research, and reminders.

Life Easy is not intended to become a generic do-everything personal assistant in its first release. Product design, roadmap, and onboarding should prioritize the job-search journey.

## Core user experience

Users can communicate through the Life Easy web dashboard and supported messaging channels. Every user has an isolated account, profile, resume, connected accounts, conversation history, and memory. The assistant should infer whether a request is job-search work or a supporting career task, then route it to the appropriate capability.

External side effects — sending email, publishing LinkedIn content, submitting applications, or changing account data — require a clear user confirmation. Research, search, matching, drafting, and summarization can run without approval.

## Deployment target

- **Web:** Next.js on Vercel.
- **API and workers:** FastAPI on Render.
- **Database:** Managed PostgreSQL with pgvector.
- **Queue/cache:** Redis-compatible managed service.
- **Files:** Private object storage for resumes and documents.
- **Messaging:** WhatsApp Business Platform (Life Easy-owned business number) and/or Telegram Bot API, subject to provider onboarding and policy.
- **Email:** Per-user OAuth connection; send from that user's mailbox after approval.
- **LinkedIn:** Supported APIs and explicitly authorized integration paths only.

Hosting free tiers have limits and may sleep, expire, or prohibit commercial use. Do not rely on ephemeral/free databases for important user data.

## Repository layout

```text
apps/
  api/       FastAPI service
  web/       Next.js dashboard
database/    PostgreSQL schema
infra/       Deployment configuration
docs/        Architecture, security, and provider setup
.github/     CI workflow
```

## Current implementation status

This repository is a foundation, not a completed SaaS. The dashboard is a starter landing/workspace UI; the API has scaffolding endpoints and a WhatsApp webhook verification/signature-validation scaffold. The webhook currently acknowledges verified events but does not yet identify users, queue work, or generate replies.

Not yet production-ready: authentication, multi-tenant authorization, persistent conversation memory, real job-source adapters, Gmail OAuth, LinkedIn integration, background workers, approvals persistence/execution, end-to-end tests, and deployment. Provider credentials and business verification must be configured by the owner. Never commit secrets.

## Security principles

- Per-user data isolation and authorization on every API route and database query.
- Encrypt OAuth refresh tokens at rest using managed keys.
- Keep secrets in hosting secret stores, never in Git or chat.
- Require explicit confirmation before external actions.
- Keep an audit trail for approvals and executed actions.
- Use rate limits, retries, idempotency, and provider quotas.
- Keep resumes, recruiter research, and conversations out of public logs.
- Provide account disconnect, data export, and deletion workflows.

## License

Proprietary personal project. Add a license only when the owner decides how the code may be reused.
