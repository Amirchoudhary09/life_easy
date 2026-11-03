"""Workable widget API (public, no key): https://apply.workable.com/api/v1/widget/accounts/{subdomain}"""

from __future__ import annotations

import asyncio

import httpx

from app.jobs.sources.base import BoardSource, JobPosting, SourceError, get_json, html_to_text, parse_dt

BASE = "https://apply.workable.com/api/v1/widget/accounts"
MAX_DETAILS = 60


class WorkableSource(BoardSource):
    name = "workable"

    async def fetch(self, client: httpx.AsyncClient, token: str) -> list[JobPosting]:
        data = await get_json(client, f"{BASE}/{token}")
        if not isinstance(data, dict):
            return []
        company = str(data.get("name") or token)
        jobs = data.get("jobs", [])[:MAX_DETAILS]

        async def detail(shortcode: str) -> str:
            try:
                d = await get_json(client, f"{BASE}/{token}/jobs/{shortcode}")
            except SourceError:
                return ""
            if not isinstance(d, dict):
                return ""
            return "\n\n".join(html_to_text(d.get(k)) for k in ("description", "requirements", "benefits") if d.get(k))

        descriptions = await asyncio.gather(*(detail(str(j.get("shortcode", ""))) for j in jobs))
        out: list[JobPosting] = []
        for j, desc in zip(jobs, descriptions, strict=False):
            loc = j.get("location") or {}
            location = ", ".join(x for x in (loc.get("city"), loc.get("region"), loc.get("country")) if x) or None
            out.append(
                JobPosting(
                    source=self.name,
                    source_job_id=str(j.get("shortcode") or j.get("code") or ""),
                    company=company,
                    title=str(j.get("title", "")),
                    apply_url=str(j.get("application_url") or j.get("url") or ""),
                    source_url=str(j.get("url") or ""),
                    description=desc,
                    location=location,
                    remote=bool(j.get("telecommuting")) or None,
                    employment_type=j.get("employment_type"),
                    posted_at=parse_dt(j.get("published_on")),
                )
            )
        return out
