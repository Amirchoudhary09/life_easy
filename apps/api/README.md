# Life Easy API

FastAPI API and background worker. Python 3.12+.

## Local setup
    python -m venv .venv
    pip install -r requirements.txt
    cp .env.example .env
    python -m app.migrate
    uvicorn app.main:app --reload

Run the background worker in a second process:
    python -m app.worker

## Routes
- /api/v1/auth: register, login, logout, current account. Browser auth uses HttpOnly cookies and CSRF checks.
- /api/v1/verification: email OTP (Resend) and phone OTP (Twilio Verify).
- /api/v1/profile: user-scoped career profile.
- /api/v1/resumes: private PDF/DOCX upload, extraction, heuristic ATS analysis and short-lived download URLs.
- /api/v1/jobs: search, save and ingestion source health.
- /api/v1/applications: user-scoped application pipeline.
- /api/v1/assistant/chat: career assistant with profile, resume and memory context.
- /api/v1/memories: user-controlled memory records.
- /api/v1/integrations: Gmail OAuth and connected-account listing.
- /api/v1/approvals: exact-content preview, confirmation and queueing.
- /api/v1/webhooks/whatsapp: Meta verification, signed inbound messages, user linking and career assistant replies.

## Secrets
See .env.example and ../../docs/provider-setup.md. Never commit secrets or ask users to paste provider credentials into chat.

## Important behavior
Approval confirmation only queues an external action. The worker re-computes the payload hash before sending. Gmail and WhatsApp send adapters are implemented; unsupported action types fail closed. Resume files are private and all resume queries are scoped by authenticated user.
