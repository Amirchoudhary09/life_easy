# API

FastAPI service intended for Render.

Run with `pip install -r requirements.txt` then `uvicorn app.main:app --reload`.

Health check: `GET /health`. Current endpoints are scaffolding. Job-source adapters, persistent approvals, identity/OAuth, and multi-user authorization must be implemented before production use.
