# WhatsApp Cloud API setup (Life Easy)

Life Easy uses one **Life Easy-owned WhatsApp Business Platform / Cloud API number** as the shared entry point. End users message it from their own personal WhatsApp accounts. Their conversations must be routed by the verified WhatsApp sender ID to a separate Life Easy user account; never use a shared admin inbox or shared memory.

## Current implementation status

- `GET /api/v1/webhooks/whatsapp`: Meta webhook verification handshake.
- `POST /api/v1/webhooks/whatsapp`: validates `X-Hub-Signature-256` against the raw request body and acknowledges valid events.
- `send_text_message()`: server-side Cloud API text-send helper.
- **Not implemented yet:** persistent sender-to-user binding, OTP/account linking, queue/worker, AI response orchestration, conversation storage, rate limits, message deduplication, opt-out handling, and production tests. The webhook currently acknowledges verified events; it does not yet reply to users.

## Required setup on your side

1. Open [Meta for Developers](https://developers.facebook.com/) and sign in with the Meta account that should own Life Easy's business assets.
2. Create a Meta app and add the WhatsApp product / Cloud API use case.
3. Create or select the Life Easy business portfolio and WhatsApp Business Account (WABA).
4. Add and verify the business phone number you want Life Easy to use. Do not assume an existing personal WhatsApp number can be used unchanged: Meta's onboarding will show whether it must be migrated or whether an eligible coexistence path is available. Do not delete or migrate an active WhatsApp account until the Meta flow clearly confirms the consequences.
5. Obtain the WABA ID, Phone Number ID, a durable System User access token with the required WhatsApp permissions, and the Meta App Secret. Keep these private.
6. Deploy the API on Render and copy its public HTTPS URL. Set the webhook callback URL to `https://YOUR-RENDER-SERVICE.onrender.com/api/v1/webhooks/whatsapp`.
7. Choose a long random webhook verify token. Add it in Render as `WHATSAPP_WEBHOOK_VERIFY_TOKEN` and enter the exact same value in Meta's webhook configuration. Subscribe the app to the `messages` webhook field.
8. Add these Render environment variables:
   - `WHATSAPP_WEBHOOK_VERIFY_TOKEN`
   - `WHATSAPP_APP_SECRET`
   - `WHATSAPP_ACCESS_TOKEN`
   - `WHATSAPP_PHONE_NUMBER_ID`
   - `WHATSAPP_GRAPH_API_VERSION` (a currently supported Graph API version shown in Meta's dashboard/docs)
9. Send a test message from a separate personal WhatsApp account after Meta webhook verification. Check Render logs for service errors only; do not log message bodies or tokens.

## Important security and product rules

- Never send OTPs, access tokens, App Secrets, or the WhatsApp two-step-verification PIN in this chat or commit them to Git.
- Configure secrets only in Render's encrypted environment-variable settings.
- The webhook must be publicly reachable over HTTPS.
- Before enabling replies, implement verified user onboarding and a unique mapping from WhatsApp `wa_id` to Life Easy `user_id`, with explicit consent and account recovery.
- Process every message under that user's tenant scope. Do not expose messages to the Life Easy operator by default.
- Use Meta's messaging policy and template requirements; outside the customer-service window, approved templates may be required.
- Keep a human approval gate for outbound job-application emails. WhatsApp messaging does not authorize sending email on a user's behalf.

## References

- [Meta WhatsApp Cloud API collection and getting-started steps](https://www.postman.com/meta/whatsapp-business-platform/documentation/wlk6lh4/whatsapp-cloud-api)
- [Meta WhatsApp messages API](https://www.postman.com/meta/whatsapp-business-platform/folder/o48mro7/messages)
