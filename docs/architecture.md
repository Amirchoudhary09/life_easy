# Architecture

## Request flow
1. User submits a task through the web or messaging channel.
2. API authenticates the user and creates a traceable task.
3. An orchestrator delegates to job discovery, profile matching, recruiter research, email drafting, and application tracking agents.
4. Provider adapters retrieve permitted data and preserve source URLs and timestamps.
5. A verifier deduplicates records and marks stale or unavailable data.
6. External actions become pending approvals; no side effect happens before explicit confirmation.
7. An idempotent worker executes approved actions and writes an audit event.

## Hosting
Next.js is deployed independently from FastAPI. Background workers run as persistent worker services. PostgreSQL is the system of record; Redis is disposable coordination/cache infrastructure.

## Provider boundaries
- Job discovery: public career pages and permitted job APIs.
- LinkedIn: approved APIs and user-authorized features only; no scraping or session-cookie automation.
- Gmail: least-privilege OAuth; draft first and send only after approval.
- Messaging: Telegram Bot API; optional approved WhatsApp Business Platform adapter.
- LLM: provider abstraction, not tied to a single model vendor.
