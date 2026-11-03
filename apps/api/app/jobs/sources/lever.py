"""Lever Postings API (public, no key): https://api.lever.co/v0/postings/{site}?mode=json"""

from __future__ import annotations

import httpx

from app.jobs.sources.base import BoardSource, JobPosting, get_json, html_to_text, parse_dt

BASE = "https://api.lever.co/v0/postings"


class LeverSource(BoardSource):
    name = "lever"

    async def fetch(self, client: httpx.AsyncClient, token: str) -> list[JobPosting]:
        data = await get_json(client, f"{BASE}/{token}", params={"mode": "json"})
        if not isinstance(data, list):
            return []
        out: list[JobPosting] = []
        for j in data:
            cats = j.get("categories") or {}
            description = j.get("descriptionPlain") or html_to_text(j.get("description"))
            extra = "\n".join(
                f"{section.get('text', '')}\n{html_to_text(section.get('content'))}" for section in (j.get("lists") or [])
            )
            out.append(
                JobPosting(
                    source=self.name,
                    source_job_id=str(j.get("id")),
                    company=token.replace("-", " ").title(),
                    title=str(j.get("text", "")),
                    apply_url=str(j.get("applyUrl") or j.get("hostedUrl") or ""),
                    source_url=str(j.get("hostedUrl") or ""),
                    description=(description + "\n\n" + extra).strip(),
                    location=cats.get("location"),
                    remote=(str(j.get("workplaceType") or "").lower() == "remote") or None,
                    employment_type=cats.get("commitment"),
                    posted_at=parse_dt(j.get("createdAt")),
                )
            )
        return out
