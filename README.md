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

Implemented in the MVP foundation branch:
- Email/password registration and login with Argon2 password hashing and short-lived JWT bearer tokens.
- Authenticated, user-scoped career profile read/update endpoints.
- Authenticated job search against jobs already indexed in PostgreSQL, explainable baseline matching, and per-user saved jobs.
- Per-message approval records bound to a hash of the exact destination/channel/message preview, explicit approve/cancel endpoint, and audit events.
- Versioned SQL migrations and a migration runner.
- Starter signup/login and signed-in career profile dashboard.
- WhatsApp webhook signature verification scaffold.

Still not complete or production-ready:
- Email and phone OTP verification, OAuth login, password reset, secure HttpOnly cookie sessions, rate limits, and abuse protection.
- Live job-source adapters and scheduled ingestion. Search currently queries the database; it does not crawl or fetch live jobs.
- Resume upload and private object storage, AI-powered parsing and advanced matching.
- WhatsApp sender-to-user binding, inbound message persistence, AI orchestration, and auto-replies.
- Gmail OAuth and send adapter, LinkedIn authorized integrations, external-action execution worker, and end-to-end delivery tests.
- Deployment, production database provisioning, secret configuration, monitoring, backups, and full security review.

The approval endpoint only records approval state. It does not send anything. No external message can be sent by this scaffold because send workers/adapters are not yet connected.
