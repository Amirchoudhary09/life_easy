# Life Easy provider setup

Enter secrets directly in Render service/worker environment or Vercel project settings. Never commit them to Git or paste passwords/OTP codes into a chat.

## Required deployment values
- DATABASE_URL: managed PostgreSQL connection string. Run the migration command after provisioning.
- JWT_SECRET: at least 32 cryptographically random bytes.
- OTP_PEPPER: separate random secret, at least 32 bytes.
- FRONTEND_ORIGIN: exact HTTPS frontend origin.

## Email OTP with Resend
1. Verify a sending domain in Resend and create an API key.
2. Set RESEND_API_KEY and RESEND_FROM_EMAIL (for example, Life Easy <verify@your-domain>).
3. Request a code from Connections → Send email OTP.

## Phone OTP with Twilio Verify
1. Create a Twilio account and Verify service.
2. Configure an approved sender/route for supported countries.
3. Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN and TWILIO_VERIFY_SERVICE_SID.
4. Use E.164 format such as +91... and request SMS OTP in Connections.

## Private resume storage
Create a private S3-compatible bucket. Set RESUME_BUCKET, S3_REGION, S3_ACCESS_KEY_ID, S3_SECRET_ACCESS_KEY and optionally S3_ENDPOINT_URL. Restrict bucket access to the API service, enable encryption and backups. Objects use per-user prefixes; downloads use short-lived signed URLs.

## AI career copilot
Set OPENAI_API_KEY and optionally OPENAI_BASE_URL and OPENAI_MODEL. Model usage is billable. User-specific profile/resume/memory context is sent to the configured endpoint.

## Gmail OAuth
1. Create a Google Cloud project and OAuth consent screen.
2. Enable Gmail API.
3. Create a Web OAuth client. Add the exact callback URL configured in GOOGLE_REDIRECT_URI to authorized redirect URIs.
4. Request minimum scopes: gmail.send, openid and email.
5. Set GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET and GOOGLE_REDIRECT_URI.
6. Generate a Fernet key and set TOKEN_ENCRYPTION_KEY. Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())".
7. Users connect their own Google account from the dashboard. Tokens are encrypted at rest. Test with a non-critical mailbox.

## WhatsApp Business Platform
1. Create a Meta app and add WhatsApp.
2. Configure a WhatsApp Business phone number and webhook URL: https://YOUR_API/api/v1/webhooks/whatsapp
3. Subscribe to messages.
4. Set WHATSAPP_WEBHOOK_VERIFY_TOKEN, WHATSAPP_APP_SECRET, WHATSAPP_ACCESS_TOKEN, WHATSAPP_PHONE_NUMBER_ID and WHATSAPP_GRAPH_API_VERSION.
5. Verify webhook subscription. Each user generates a one-time link code in the dashboard and sends LINK followed by that displayed code to the business number.
6. Review Meta business verification, templates, conversation pricing and policy requirements.

## Job ingestion
Set GREENHOUSE_BOARD_TOKENS and LEVER_SITE_NAMES to comma-separated public employer board identifiers. The worker fetches postings every JOB_INGESTION_INTERVAL_SECONDS (default six hours), upserts them and records source runs. Do not scrape LinkedIn or bypass access controls.

## Deployment order
1. Create managed PostgreSQL and private object storage.
2. Configure API and worker environment variables in Render.
3. Deploy API, then run migrations once with the production database URL.
4. Deploy the worker using python -m app.worker.
5. Deploy Next.js to Vercel with NEXT_PUBLIC_API_BASE_URL and matching FRONTEND_ORIGIN.
6. Configure custom HTTPS domains. Prefer frontend and API hostnames under the same registrable domain for reliable cookie behavior. Restrict credentialed CORS to the frontend origin.
7. Test registration, cookie login/logout, CSRF, OTP, resume upload/download, job ingestion, Gmail OAuth, WhatsApp webhook and approval send with test accounts.

Do not deploy with placeholder secrets. Verify each provider integration before enabling it for users.
