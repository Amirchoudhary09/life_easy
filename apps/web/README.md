# Life Easy dashboard

Next.js 15 (App Router) + TypeScript. No UI library; styles are in `app/globals.css`.

```bash
npm ci
echo NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 > .env.local
npm run dev            # http://localhost:3000
npm run typecheck && npm run build
```

Pages: `/` landing, `/login`, `/register`, and the signed-in app under `/app`: Chat, Matches, Jobs, Tracker, Approvals, Resumes, Settings.

- `lib/api.ts`: typed API client. The access token is kept in memory only; the refresh token is kept in `localStorage` so a reload stays signed in (wrapped in try/catch for blocked storage). On a 401 the client refreshes once and retries.
- `components/ApprovalCard.tsx`: shows the exact channel, destination, subject, body, attachments and content hash of an outbound action. Approve sends that hash, so the server refuses if the content changed. Edit creates a new preview.

Deploy on Vercel with the project root set to `apps/web` and `NEXT_PUBLIC_API_BASE_URL` set to the API URL (it is baked in at build time).
