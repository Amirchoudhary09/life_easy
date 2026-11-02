# Life Easy

Life Easy is a multi-user, career-first AI assistant. It combines job discovery, resume intelligence, application tracking, a career copilot, WhatsApp conversations and approved career communications.

## Product modules
- Email/password registration and login. Browser sessions use HttpOnly cookies with CSRF protection.
- Email OTP (Resend) and phone OTP (Twilio Verify) account verification.
- User-isolated profiles, resumes, saved jobs, applications, conversations and memories.
- Private PDF/DOCX resume storage on S3-compatible storage, text extraction, skill detection and transparent heuristic ATS-style analysis.
- Job ingestion from public Greenhouse and Lever company boards; normalized jobs are matched against each user's skills and preferences.
- Career copilot powered by an OpenAI-compatible chat completion endpoint, with user-specific profile/resume/memory context.
- WhatsApp Business webhook signature validation, one-time account linking, inbound routing and assistant replies.
- Gmail OAuth using each user's own Google account. OAuth tokens are encrypted at rest.
- Exact-message approval previews. Approval binds destination, channel and body to a SHA-256 content hash. A separate worker re-checks the hash before sending Gmail or WhatsApp messages.

## Architecture
- Web: Next.js 15, deployed on Vercel.
- API: FastAPI + asyncpg, deployed as a Render web service.
- Worker: separate Render background worker for scheduled job ingestion and approved message delivery.
- Database: managed PostgreSQL. Migrations live in apps/api/migrations.
- Resume storage: private S3-compatible bucket.
- Queue: PostgreSQL-backed action queue for the first release.

## Local setup
1. Create a PostgreSQL database with pgvector extension available.
2. Copy apps/api/.env.example to apps/api/.env. Set DATABASE_URL, JWT_SECRET (32+ random bytes) and OTP_PEPPER (a separate 32+ random bytes).
3. Install and migrate the API:
   
       cd apps/api
       pip install -r requirements.txt
       python -m app.migrate
       uvicorn app.main:app --reload

4. Configure the web app:
   
       cd apps/web
       cp .env.example .env.local
       # Set NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
       npm install
       npm run dev

5. Run the worker in another terminal from apps/api:
   
       python -m app.worker

## Provider configuration
See docs/provider-setup.md for email OTP, SMS OTP, Gmail OAuth, WhatsApp Business, private storage and AI setup. Credentials belong in hosting secret stores, never in Git or chat.

## Current honest limitations
- Greenhouse and Lever ingestion requires configured public company board tokens/site names. It does not scrape LinkedIn or private job boards.
- ATS analysis is a transparent heuristic, not a proprietary vendor ATS score.
- Gmail send and WhatsApp replies require provider setup and user authorization. LinkedIn outbound actions are not implemented; LinkedIn assistance is limited to drafting/research.
- OAuth disconnect/revocation UI, password reset, stronger abuse/rate limiting, admin board management, observability, backup policy and external penetration testing remain before public production launch.
- Configure HTTPS frontend/API origins for credentialed CORS. Prefer custom app/api domains under the same registrable domain for reliable browser cookie behavior.

## Development checks
- API tests: cd apps/api && pytest -q
- API syntax: python -m compileall -q apps/api/app
- Web: cd apps/web && npm install && npm run build

Do not deploy with placeholder secrets. Run migrations against the production database before starting the API and worker.
