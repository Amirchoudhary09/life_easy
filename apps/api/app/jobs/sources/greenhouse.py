"""Greenhouse Job Board API (public, no key): https://boards-api.greenhouse.io/v1/boards/{token}/jobs"""

from __future__ import annotations

import httpx

from app.jobs.sources.base import BoardSource, JobPosting, get_json, html_to_text, parse_dt

BASE = "https://boards-api.greenhouse.io/v1/boards"


class GreenhouseSource(BoardSource):
    name = "greenhouse"

    async def fetch(self, client: httpx.AsyncClient, token: str) -> list[JobPosting]:
        meta = await get_json(client, f"{BASE}/{token}")
        company = str(meta.get("name") or token) if isinstance(meta, dict) else token
        data = await get_json(client, f"{BASE}/{token}/jobs", params={"content": "true"})
        jobs = data.get("jobs", []) if isinstance(data, dict) else []
        out: list[JobPosting] = []
        for j in jobs:
            location = (j.get("location") or {}).get("name")
            metadata = {str(x.get("name", "")).lower(): x.get("value") for x in (j.get("metadata") or []) if isinstance(x, dict)}
            out.append(
                JobPosting(
                    source=self.name,
                    source_job_id=str(j.get("id")),
                    company=company,
                    title=str(j.get("title", "")),
                    apply_url=str(j.get("absolute_url", "")),
                    source_url=str(j.get("absolute_url", "")),
                    description=html_to_text(j.get("content")),
                    location=location,
                    employment_type=str(metadata.get("employment type") or metadata.get("job type") or "") or None,
                    posted_at=parse_dt(j.get("first_published") or j.get("updated_at")),
                )
            )
        return out
