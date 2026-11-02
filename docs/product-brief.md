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
