"""Adzuna search API (free key): https://developer.adzuna.com/ - covers India (country=in) and 15+ others."""

from __future__ import annotations

import httpx

from app.config import get_settings
from app.jobs.sources.base import JobPosting, SearchSource, get_json, html_to_text, parse_dt

BASE = "https://api.adzuna.com/v1/api/jobs"


class AdzunaSource(SearchSource):
    name = "adzuna"

    def configured(self) -> bool:
        s = get_settings()
        return bool(s.adzuna_app_id and s.adzuna_app_key)

    async def search(
        self, client: httpx.AsyncClient, *, what: str, where: str | None, max_days_old: int = 7, limit: int = 50
    ) -> list[JobPosting]:
        s = get_settings()
        params: dict[str, str | int] = {
            "app_id": s.adzuna_app_id,
            "app_key": s.adzuna_app_key,
            "what": what,
            "results_per_page": min(limit, 50),
            "max_days_old": max_days_old,
            "content-type": "application/json",
        }
        if where:
            params["where"] = where
        data = await get_json(client, f"{BASE}/{s.adzuna_country}/search/1", params=params)
        results = data.get("results", []) if isinstance(data, dict) else []
        out: list[JobPosting] = []
        for j in results:
            salary = None
            if j.get("salary_min") or j.get("salary_max"):
                salary = f"{int(j.get('salary_min') or 0):,} - {int(j.get('salary_max') or 0):,}"
            out.append(
                JobPosting(
                    source=self.name,
                    source_job_id=str(j.get("id", "")),
                    company=str((j.get("company") or {}).get("display_name") or "Unknown"),
                    title=str(j.get("title", "")),
                    apply_url=str(j.get("redirect_url", "")),
                    source_url=str(j.get("redirect_url", "")),
                    description=html_to_text(j.get("description")),
                    location=(j.get("location") or {}).get("display_name"),
                    employment_type=j.get("contract_time") or j.get("contract_type"),
                    salary_text=salary,
                    posted_at=parse_dt(j.get("created")),
                )
            )
        return out
