from __future__ import annotations

import hashlib
import html
import re
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx

_TAG = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.S | re.I)
_BR = re.compile(r"<\s*(br|/p|/div|/li|/h[1-6]|/tr)\s*/?>", re.I)
_ANY_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t   ]+")  # incl. non-breaking spaces from &nbsp;
_NL = re.compile(r"\n{3,}")

MAX_DESCRIPTION = 20000


def html_to_text(raw: str | None) -> str:
    if not raw:
        return ""
    # Some APIs (Greenhouse) return the HTML itself entity-escaped: decode it first so tags can be stripped.
    if "&lt;" in raw and "<" not in raw:
        raw = html.unescape(raw)
    text = _TAG.sub("", raw)
    text = _BR.sub("\n", text)
    text = _ANY_TAG.sub(" ", text)
    text = html.unescape(text)
    text = _WS.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    text = _NL.sub("\n\n", text).strip()
    return text[:MAX_DESCRIPTION]


def parse_dt(value: str | int | float | None) -> datetime | None:
    if value is None or value == "":
        return None
    try:
        if isinstance(value, int | float):
            ts = float(value)
            if ts > 1e12:  # milliseconds
                ts /= 1000.0
            return datetime.fromtimestamp(ts, tz=UTC)
        s = str(value).strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    except (ValueError, OverflowError):
        return None


def normalize_employment_type(value: str | None) -> str | None:
    if not value:
        return None
    v = value.lower()
    if "intern" in v:
        return "internship"
    if "part" in v:
        return "part-time"
    if "contract" in v or "freelance" in v or "temporary" in v:
        return "contract"
    if "full" in v or "permanent" in v:
        return "full-time"
    return v[:60]


def looks_remote(*texts: str | None) -> bool:
    blob = " ".join(t for t in texts if t).lower()
    return "remote" in blob or "work from home" in blob or "anywhere" in blob


@dataclass
class JobPosting:
    source: str
    source_job_id: str
    company: str
    title: str
    apply_url: str
    description: str = ""
    location: str | None = None
    remote: bool | None = None
    employment_type: str | None = None
    salary_text: str | None = None
    source_url: str | None = None
    posted_at: datetime | None = None

    def __post_init__(self) -> None:
        self.title = (self.title or "").strip()[:300]
        self.company = (self.company or "").strip()[:200] or self.source
        self.location = (self.location or None) and self.location.strip()[:200]
        self.apply_url = (self.apply_url or self.source_url or "").strip()[:1000]
        if not self.source_job_id:
            self.source_job_id = hashlib.sha256(self.apply_url.encode()).hexdigest()[:32]
        self.source_job_id = str(self.source_job_id)[:200]
        if self.remote is None:
            self.remote = looks_remote(self.location, self.title)
        self.employment_type = normalize_employment_type(self.employment_type)

    @property
    def content_hash(self) -> str:
        blob = "|".join([self.title, self.company, self.location or "", self.description[:5000]])
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def embedding_text(self) -> str:
        return f"{self.title}\n{self.company}\n{self.location or ''}\n{self.description[:4000]}"


class SourceError(Exception):
    pass


class BoardSource:
    """One company's public job board (token = board slug)."""

    name = "board"

    async def fetch(self, client: httpx.AsyncClient, token: str) -> list[JobPosting]:
        raise NotImplementedError


class SearchSource:
    """Keyword search across many companies."""

    name = "search"

    def configured(self) -> bool:
        return False

    async def search(
        self, client: httpx.AsyncClient, *, what: str, where: str | None, max_days_old: int = 7, limit: int = 50
    ) -> list[JobPosting]:
        raise NotImplementedError


async def get_json(client: httpx.AsyncClient, url: str, **kwargs: object) -> object:
    try:
        resp = await client.get(url, **kwargs)  # type: ignore[arg-type]
    except httpx.HTTPError as exc:
        raise SourceError(f"{url}: {type(exc).__name__}") from exc
    if resp.status_code == 404:
        raise SourceError(f"{url}: board not found")
    if resp.is_error:
        raise SourceError(f"{url}: HTTP {resp.status_code}")
    try:
        return resp.json()
    except ValueError as exc:
        raise SourceError(f"{url}: invalid JSON") from exc
