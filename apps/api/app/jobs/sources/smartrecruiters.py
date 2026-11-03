"""SmartRecruiters Posting API (public, no key): https://api.smartrecruiters.com/v1/companies/{id}/postings"""

from __future__ import annotations

import asyncio

import httpx

from app.jobs.sources.base import BoardSource, JobPosting, SourceError, get_json, html_to_text, parse_dt

BASE = "https://api.smartrecruiters.com/v1/companies"
MAX_DETAILS = 60


class SmartRecruitersSource(BoardSource):
    name = "smartrecruiters"

    async def fetch(self, client: httpx.AsyncClient, token: str) -> list[JobPosting]:
        data = await get_json(client, f"{BASE}/{token}/postings", params={"limit": 100})
        items = data.get("content", []) if isinstance(data, dict) else []
        items = items[:MAX_DETAILS]

        async def detail(posting_id: str) -> tuple[str, str]:
            try:
                d = await get_json(client, f"{BASE}/{token}/postings/{posting_id}")
            except SourceError:
                return "", ""
            if not isinstance(d, dict):
                return "", ""
            sections = (d.get("jobAd") or {}).get("sections") or {}
            text = "\n\n".join(
                html_to_text((sections.get(k) or {}).get("text"))
                for k in ("jobDescription", "qualifications", "additionalInformation")
            )
            return text.strip(), str(d.get("applyUrl") or "")

        details = await asyncio.gather(*(detail(str(j.get("id", ""))) for j in items))
        out: list[JobPosting] = []
        for j, (desc, apply_url) in zip(items, details, strict=False):
            loc = j.get("location") or {}
            location = ", ".join(x for x in (loc.get("city"), loc.get("region"), loc.get("country")) if x) or None
            out.append(
                JobPosting(
                    source=self.name,
                    source_job_id=str(j.get("id", "")),
                    company=str((j.get("company") or {}).get("name") or token),
                    title=str(j.get("name", "")),
                    apply_url=apply_url or f"https://jobs.smartrecruiters.com/{token}/{j.get('id', '')}",
                    source_url=f"https://jobs.smartrecruiters.com/{token}/{j.get('id', '')}",
                    description=desc,
                    location=location,
                    remote=bool(loc.get("remote")) or None,
                    employment_type=(j.get("typeOfEmployment") or {}).get("label"),
                    posted_at=parse_dt(j.get("releasedDate")),
                )
            )
        return out
