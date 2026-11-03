"""Request-ID middleware: accept X-Request-ID or mint one; echo it back; bind it to logs."""

from __future__ import annotations

import contextvars
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

_request_id: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")


def current_request_id() -> str:
    return _request_id.get()


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        incoming = request.headers.get("x-request-id", "")
        rid = incoming[:64] if incoming and incoming.isprintable() else uuid.uuid4().hex
        token = _request_id.set(rid)
        structlog.contextvars.bind_contextvars(request_id=rid)
        try:
            response = await call_next(request)
        finally:
            structlog.contextvars.unbind_contextvars("request_id")
            _request_id.reset(token)
        response.headers["X-Request-ID"] = rid
        return response
