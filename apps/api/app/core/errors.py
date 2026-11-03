"""Domain errors mapped to HTTP responses in app.main."""

from __future__ import annotations


class AppError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(self, message: str = "", **extra: object) -> None:
        super().__init__(message or self.code)
        self.message = message or self.code
        self.extra = extra


class NotFound(AppError):
    status_code = 404
    code = "not_found"


class Forbidden(AppError):
    status_code = 403
    code = "forbidden"


class Conflict(AppError):
    status_code = 409
    code = "conflict"


class Unauthorized(AppError):
    status_code = 401
    code = "unauthorized"


class ProviderNotConfigured(AppError):
    status_code = 503
    code = "provider_not_configured"


class ProviderError(AppError):
    status_code = 502
    code = "provider_error"


class LimitExceeded(AppError):
    status_code = 429
    code = "limit_exceeded"
