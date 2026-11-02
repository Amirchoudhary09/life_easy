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


- [ ] Enforce a global per-message approval gate for every outbound communication to another person/audience across email, LinkedIn, WhatsApp/SMS, and other connected channels.
- [ ] Approval preview must bind exact channel, recipient/audience, full message body, and attachments; invalidate approval if any field changes.
- [ ] Store approval evidence, content hash, timestamp, destination, execution result, and idempotency key. Never treat silence or standing consent as approval.
