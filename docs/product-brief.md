# Product Brief — Life Easy

## Positioning
Life Easy is a career-first personal AI assistant. Its primary job is to help each user find and secure better career opportunities. Supporting features help the user communicate and manage career-related work.

## Primary user journey
1. Create an account and verify email/phone.
2. Upload resume and confirm skills, experience, target roles, locations, salary, and work mode.
3. Connect a messaging channel and optionally connect Gmail.
4. Ask for jobs naturally by chat or dashboard.
5. Review ranked opportunities with source links and match explanations.
6. Save roles, research recruiters, prepare tailored applications.
7. Approve emails before sending from the user's connected mailbox.
8. Track application stages and schedule follow-ups.

## Product modules
### P0 — Job hunting
- User profile and resume ingestion
- Job discovery from permitted sources
- Deduplication and freshness checks
- Resume-to-job matching with explanations
- Saved jobs and application tracking
- Recruiter research with public-source evidence

### P1 — Career communications
- Gmail OAuth per user
- Personalized application/recruiter email drafts
- Approval-gated email sending
- LinkedIn post, connection note, recruiter message, and profile-content drafting
- LinkedIn execution only through supported authorized access paths

### P2 — Career growth
- Interview preparation and mock interviews
- Company and role research
- Resume and cover-letter tailoring
- Follow-up reminders and career activity analytics

## Product guardrails
- Job hunting remains the home-screen priority and largest product surface.
- Do not build generic personal finance, shopping, health, or home-control agents in the first product scope.
- Do not scrape LinkedIn or bypass provider access controls.
- Never guess recruiter emails or private phone numbers.
- Require explicit approval before sending, publishing, submitting, or changing external data.
- Keep each user's profile, messages, memory, files, and connected accounts isolated.
- Users connect their own Gmail; Life Easy's WhatsApp business number is only a shared messaging entry point, not a shared customer inbox.

## Current status
This brief defines the intended product direction. It does not mean the listed integrations or product capabilities are already implemented.


## Mandatory final-send approval (global policy)

**No outbound message to another person or external audience may be sent or published until the user reviews the exact final content and explicitly approves that specific send.** This applies to email, LinkedIn messages and posts, recruiter outreach, WhatsApp/SMS messages initiated on the user's behalf, and other connected communication channels.

Approval flow:
1. Prepare the message and resolve its destination/audience.
2. Show the exact recipient or audience, channel, complete message body, and any attachments.
3. Ask a clear confirmation question such as: "Send this exact message to [recipient] via [channel]?"
4. Execute only after an unambiguous affirmative response tied to that preview.
5. If the user edits the content, recipient, audience, or attachment, invalidate the previous approval and show the revised preview for approval again.
6. Record the approval, content hash, destination, timestamp, execution result, and idempotency key in the audit log.
7. Never infer approval from silence, prior approvals, a general instruction, or an earlier approval for a different message.

This is a per-message approval rule, not a one-time account setting. Users may ask Life Easy to draft, revise, research, or queue messages automatically, but not to bypass the final-send approval.

**Exception:** ordinary conversational replies that Life Easy sends back to the user in the user's own active chat are part of the assistant interaction and do not require a second approval. This exception does not apply to messages sent to other people, groups, public feeds, or external services on the user's behalf.
