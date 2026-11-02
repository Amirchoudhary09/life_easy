# Life Easy Architecture — Career-first

## Product priority

Job hunting is the primary workflow. Email, LinkedIn, documents, interview preparation, and reminders are supporting capabilities that help users progress through their job search and career development. Avoid expanding the first release into a generic personal assistant.

## High-level request flow

1. A user sends a request through the web dashboard or a connected messaging channel.
2. The API authenticates the user and resolves the user's tenant context.
3. The intent router classifies the request:
   - **Job hunting:** discovery, profile/resume matching, recruiter research, application tracking, interview preparation, follow-ups.
   - **Career productivity:** email drafting, LinkedIn content, resume/cover-letter editing, career research, reminders.
4. A task planner delegates to narrowly scoped agents/tools.
5. Provider adapters retrieve permitted data and preserve source URLs, timestamps, and provenance.
6. A verifier deduplicates results, checks freshness, and marks uncertainty.
7. Drafts and other external side effects are placed in an approval queue.
8. Only after explicit user confirmation does an idempotent worker execute the action and write an audit event.

## Core modules

- **Job Discovery Agent:** public job boards, permitted APIs, and company career pages.
- **Profile & Match Agent:** resume parsing, skill normalization, eligibility and match explanations.
- **Recruiter Research Agent:** publicly available professional contact details with source citations; never infer or guess email addresses.
- **Application Tracker:** saved jobs, application stages, interviews, follow-ups, and outcomes.
- **Career Email Agent:** per-user Gmail OAuth; draft by default, send only after approval.
- **LinkedIn Career Agent:** prepare posts, connection notes, recruiter messages, and profile copy. Execute publishing/actions only through currently supported authorized APIs or user-mediated flows. No scraping, session-cookie extraction, or browser automation that bypasses platform restrictions.
- **Career Coach:** interview practice, company research, resume and cover-letter tailoring.

## Multi-tenant identity and memory

Every user-owned record must carry a user ID and be scoped by the authenticated identity. Messaging identities (provider + sender ID) map to exactly one verified Life Easy user. Each user's resume, preferences, OAuth connections, conversations, memory, approvals, and application history remain isolated. Never use the Life Easy operator's inbox as a shared customer inbox.

## Hosting

- Next.js web dashboard on Vercel.
- FastAPI API on Render.
- Persistent background worker service on Render (not long-running work inside a request handler).
- Managed PostgreSQL + pgvector as system of record.
- Managed Redis for queues, rate limits, and disposable cache.
- Private object storage for resumes and generated documents.

## External action policy

Research, searching, matching, summarizing, and drafting can run automatically. Sending an email, publishing a LinkedIn post, submitting an application, or making a consequential account change requires a clear approval tied to a preview of the exact action. Record actor, target, timestamp, result, and idempotency key.

## Provider boundaries

- Job discovery: permitted public APIs, public company career pages, and job boards.
- LinkedIn: approved APIs and user-authorized features only; no scraping or session-cookie automation.
- Gmail: least-privilege OAuth; draft first and send only after approval.
- Messaging: official WhatsApp Business Platform and/or Telegram Bot API, subject to provider policies.
- LLM: provider abstraction; do not couple business logic to one model vendor.

## Delivery phases

1. Authentication, verified onboarding, tenant isolation, profile and resume.
2. Job discovery, matching, saved jobs, application tracker.
3. WhatsApp/Telegram routing and per-user conversation context.
4. Recruiter research and career email drafts with approval.
5. LinkedIn career content through supported authorized pathways.
6. Interview preparation, analytics, security hardening, observability, and production deployment.


## Mandatory approval before every external message

Every outbound communication to another person or audience must pass a final per-message approval gate, regardless of channel (Gmail, LinkedIn, WhatsApp/SMS, or another connected provider). The approval preview must include the exact destination/audience, channel, full final text, and attachments. Any change to these invalidates approval. Only an explicit confirmation tied to the exact preview can authorize sending. Persist an audit record and idempotency key. No standing consent or blanket "send automatically" permission can bypass this gate.

Routine replies from Life Easy to the user in the same active assistant conversation are exempt so normal chat remains usable. This exception never covers third-party recipients, group messages, or public posts.
