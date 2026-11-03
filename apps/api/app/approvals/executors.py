"""Importing this module registers every executor with the approval service."""

from __future__ import annotations

import app.email.service  # noqa: F401  registers send_email
import app.linkedin.service  # noqa: F401  registers linkedin_post / linkedin_message
