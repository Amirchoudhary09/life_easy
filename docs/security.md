# Security checklist

Status as of the current branch. `[x]` = implemented and covered by tests unless noted; `[~]` = partly done; `[ ]` = open.

## Identity and access

- [x] Per-user accounts: email + password (Argon2id), 60-minute JWT access tokens, rotating refresh tokens stored only as SHA-256 hashes, logout / logout-everywhere. *(Social login / OIDC is not added.)*
- [x] Every user-owned table carries `user_id`; every route resolves the user from the token and scopes queries by it (isolation tests for profile, approvals, resumes, chat approvals).
- [ ] Postgres row-level security as a second line of defence.
- [x] Messaging identities (WhatsApp `wa_id`, Telegram chat id) bind to one user only through a one-time dashboard code (15 minutes, single use); `STOP` unlinks.

## Webhooks

- [x] WhatsApp `X-Hub-Signature-256` HMAC check on the raw body; Telegram secret-token header check. Verification never depends on the swappable delivery adapter.
- [x] Replay / retry protection: every provider message id is recorded once (`processed_events`), duplicates are ignored.
- [~] No timestamp window on WhatsApp events (signature + de-duplication only).

## Secrets and data at rest

- [x] OAuth access/refresh tokens and IMAP app passwords encrypted with Fernet (`TOKEN_ENCRYPTION_KEY`); disconnect wipes them.
- [~] The key lives in the hosting secret store, not a KMS; rotating it means re-connecting accounts.
- [x] Production refuses to start with the default `JWT_SECRET`, without `TOKEN_ENCRYPTION_KEY`, on SQLite, without Redis, or with the fake AI.
- [x] `.env` files are git-ignored; only `.env.example` with empty values is committed.
- [x] Uploads go to private object storage (or a local folder); downloads stream through the API after an ownership check. *(No pre-signed URLs are issued.)*
- [x] Upload limits: 5 MB, PDF/DOCX/TXT/MD only.

## Logging and abuse

- [x] Structured logs with request ids; keys such as `password`, `token`, `body`, `text`, `phone` are redacted; message bodies and resume text are not logged.
- [x] Rate limits per route and client (login, register, uploads, drafts, chat, ingest) via Redis or memory, plus a per-user daily AI call cap.
- [ ] Error tracking (e.g. Sentry) with PII scrubbing.

## Outbound actions (approval gate)

- [x] Global per-message approval gate: email, LinkedIn posts and messages all go through `action_approvals`; the agent's tools can only create previews.
- [x] The preview binds channel, from, to/cc/audience, subject, full body and attachments into a SHA-256 `content_hash`; the web approve call must send the hash it showed; any edit rejects the old approval and creates a new one.
- [x] Each approval executes once (`approved → executing → executed|failed`), with an idempotency key passed to the provider, and expires after 48 hours.
- [x] Approval evidence (who, via which channel, hash, time, result or error) is written to the insert-only `audit_events` table. Silence or standing consent never approves anything.
- [x] Text from job posts, emails, web pages and resumes is wrapped as `<untrusted_content>` for the model and cannot trigger an action by itself.

## Retention and user rights

- [x] Export of everything stored about the user (JSON, no secrets or embeddings).
- [x] Account deletion: immediate lock-out and channel unlink, then a background purge of files and rows.
- [x] Recruiter contacts are kept with their source and deleted after 90 days.
- [ ] Retention period for conversations and audit events (currently kept until account deletion).

## Operations

- [x] CORS restricted to `FRONTEND_ORIGIN`.
- [x] API container runs as a non-root user.
- [ ] Database backups and a tested restore (configure on the managed Postgres plan).
- [ ] Dependency update policy (Dependabot or similar).
