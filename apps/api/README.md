# API

FastAPI service intended for Render.

Run with `pip install -r requirements.txt` then `uvicorn app.main:app --reload`.

- Health check: `GET /health`.
- WhatsApp webhook: `GET/POST /api/v1/webhooks/whatsapp` (Meta verification and signature validation).
- WhatsApp setup checklist: [../../docs/whatsapp-setup.md](../../docs/whatsapp-setup.md).

Current endpoints are scaffolding. The WhatsApp webhook validates and acknowledges events but does not yet route users or generate AI replies. Job-source adapters, persistent approvals, identity/OAuth, queue workers, and multi-user authorization must be implemented before production use.
