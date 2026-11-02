# Security checklist

- [ ] Replace development API-key auth with per-user OAuth/OIDC.
- [ ] Verify webhook signatures and enforce replay protection.
- [ ] Encrypt OAuth refresh tokens with a managed key.
- [ ] Scope every query by authenticated user ID.
- [ ] Store uploads in private object storage with short-lived signed URLs.
- [ ] Redact secrets, tokens, email bodies, and resume text from logs.
- [ ] Add rate limiting and abuse controls.
- [ ] Add approval records and immutable audit events for external actions.
- [ ] Use idempotency keys for messaging and email sends.
- [ ] Configure database backups and test restore procedures.
- [ ] Add retention and account-deletion workflows.
- [ ] Restrict CORS to the deployed frontend origin.
- [ ] Rotate credentials through hosting secret stores; never commit .env.
