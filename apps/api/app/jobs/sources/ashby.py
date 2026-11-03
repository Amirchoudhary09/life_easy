"""Ashby Job Posting API (public, no key): https://api.ashbyhq.com/posting-api/job-board/{name}"""

from __future__ import annotations

import httpx

from app.jobs.sources.base import BoardSource, JobPosting, get_json, html_to_text, parse_dt

BASE = "https://api.ashbyhq.com/posting-api/job-board"


class AshbySource(BoardSource):
    name = "ashby"

    async def fetch(self, client: httpx.AsyncClient, token: str) -> list[JobPosting]:
        data = await get_json(client, f"{BASE}/{token}", params={"includeCompensation": "true"})
        jobs = data.get("jobs", []) if isinstance(data, dict) else []
        out: list[JobPosting] = []
        for j in jobs:
            comp = (j.get("compensation") or {}).get("compensationTierSummary")
            out.append(
                JobPosting(
                    source=self.name,
                    source_job_id=str(j.get("id")),
                    company=token.replace("-", " ").title(),
                    title=str(j.get("title", "")),
                    apply_url=str(j.get("applyUrl") or j.get("jobUrl") or ""),
                    source_url=str(j.get("jobUrl") or ""),
                    description=j.get("descriptionPlain") or html_to_text(j.get("descriptionHtml")),
                    location=j.get("location"),
                    remote=bool(j.get("isRemote")) or None,
                    employment_type=j.get("employmentType"),
                    salary_text=str(comp) if comp else None,
                    posted_at=parse_dt(j.get("publishedAt")),
                )
            )
        return out
