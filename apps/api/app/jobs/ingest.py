"""Fetch postings from configured sources, de-duplicate and upsert them with embeddings."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings import get_embeddings
from app.config import get_settings
from app.core.logging import get_logger
from app.db import models as m
from app.db.session import get_session_factory
from app.jobs.sources import BOARD_SOURCES, SEARCH_SOURCES, JobPosting
from app.jobs.sources.base import SourceError

log = get_logger(__name__)
STALE_AFTER_DAYS = 14


async def upsert_postings(session: AsyncSession, postings: list[JobPosting]) -> dict[str, int]:
    """Insert new jobs, refresh changed ones, touch unchanged ones. Returns counts."""
    counts = {"new": 0, "updated": 0, "unchanged": 0}
    if not postings:
        return counts
    seen: dict[tuple[str, str], JobPosting] = {}
    for p in postings:
        if p.title and p.apply_url:
            seen[(p.source, p.source_job_id)] = p  # last one wins
    keys = list(seen)
    existing: dict[tuple[str, str], m.Job] = {}
    for i in range(0, len(keys), 500):
        chunk = keys[i : i + 500]
        rows = (
            await session.scalars(
                select(m.Job).where(m.Job.source.in_({k[0] for k in chunk}), m.Job.source_job_id.in_({k[1] for k in chunk}))
            )
        ).all()
        for row in rows:
            existing[(row.source, row.source_job_id)] = row
    now = datetime.now(UTC)
    to_embed: list[tuple[m.Job, str]] = []
    for key, p in seen.items():
        row = existing.get(key)
        if row is None:
            row = m.Job(
                source=p.source,
                source_job_id=p.source_job_id,
                company=p.company,
                title=p.title,
                location=p.location,
                remote=p.remote,
                employment_type=p.employment_type,
                salary_text=p.salary_text,
                description=p.description,
                apply_url=p.apply_url,
                source_url=p.source_url,
                posted_at=p.posted_at,
                content_hash=p.content_hash,
                fetched_at=now,
                last_seen_at=now,
                is_active=True,
            )
            session.add(row)
            to_embed.append((row, p.embedding_text()))
            counts["new"] += 1
        elif row.content_hash != p.content_hash:
            row.company, row.title, row.location = p.company, p.title, p.location
            row.remote, row.employment_type, row.salary_text = p.remote, p.employment_type, p.salary_text
            row.description, row.apply_url, row.source_url = p.description, p.apply_url, p.source_url
            row.posted_at = p.posted_at or row.posted_at
            row.content_hash = p.content_hash
            row.last_seen_at = now
            row.is_active = True
            to_embed.append((row, p.embedding_text()))
            counts["updated"] += 1
        else:
            row.last_seen_at = now
            row.is_active = True
            counts["unchanged"] += 1
    if to_embed:
        vectors = await get_embeddings().embed([t for _, t in to_embed])
        for (row, _), vec in zip(to_embed, vectors, strict=False):
            row.embedding = vec
    await session.flush()
    return counts


async def deactivate_stale(session: AsyncSession, *, sources: set[str]) -> int:
    cutoff = datetime.now(UTC) - timedelta(days=STALE_AFTER_DAYS)
    result = await session.execute(
        update(m.Job)
        .where(m.Job.source.in_(sources), m.Job.last_seen_at < cutoff, m.Job.is_active.is_(True))
        .values(is_active=False)
    )
    return result.rowcount or 0


async def _search_queries(session: AsyncSession) -> list[tuple[str, str | None]]:
    """Distinct (title, location) pairs from active users' preferences, capped to keep API usage small."""
    profiles = (await session.scalars(select(m.Profile).where(m.Profile.digest_enabled.is_(True)))).all()
    pairs: list[tuple[str, str | None]] = []
    for p in profiles:
        prefs = p.preferences or {}
        titles = [t for t in prefs.get("titles", []) if isinstance(t, str) and t.strip()] or ([p.headline] if p.headline else [])
        locations = [loc for loc in prefs.get("locations", []) if isinstance(loc, str)] or [p.location or ""]
        for t in titles[:3]:
            for loc in locations[:2]:
                pair = (t.strip()[:80], (loc or "").strip()[:80] or None)
                if pair not in pairs:
                    pairs.append(pair)
    return pairs[:20]


async def run_ingest(only: list[str] | None = None) -> dict[str, Any]:
    settings = get_settings()
    report: dict[str, Any] = {"boards": {}, "search": {}, "errors": []}
    async with httpx.AsyncClient(
        timeout=30.0, headers={"User-Agent": "LifeEasy/1.0 (+job discovery)"}, follow_redirects=True
    ) as client:
        async with get_session_factory()() as session:
            active_sources: set[str] = set()
            for provider, token in settings.job_board_list:
                if only and provider not in only:
                    continue
                source = BOARD_SOURCES.get(provider)
                if source is None:
                    report["errors"].append(f"unknown board provider {provider}")
                    continue
                try:
                    postings = await source.fetch(client, token)
                    report["boards"][f"{provider}:{token}"] = await upsert_postings(session, postings)
                    active_sources.add(provider)
                except SourceError as exc:
                    report["errors"].append(str(exc))
                    log.warning("board fetch failed", provider=provider, error=str(exc))
            adzuna = SEARCH_SOURCES["adzuna"]
            if adzuna.configured() and (not only or "adzuna" in only):
                for what, where in await _search_queries(session):
                    try:
                        postings = await adzuna.search(client, what=what, where=where)
                        report["search"][f"{what}@{where or '*'}"] = await upsert_postings(session, postings)
                    except SourceError as exc:
                        report["errors"].append(str(exc))
            if active_sources:
                report["deactivated"] = await deactivate_stale(session, sources=active_sources)
            await session.commit()
    log.info("ingest finished", boards=len(report["boards"]), searches=len(report["search"]), errors=len(report["errors"]))
    return report
