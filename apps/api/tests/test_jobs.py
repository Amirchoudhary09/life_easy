from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import respx
from app.ai.llm import FakeLLM, set_llm
from app.db import models as m
from app.jobs.ingest import deactivate_stale, run_ingest, upsert_postings
from app.jobs.matching import refresh_matches_for_user
from app.jobs.sources.base import JobPosting, html_to_text, looks_remote, normalize_employment_type, parse_dt
from app.jobs.sources.greenhouse import GreenhouseSource
from app.jobs.sources.lever import LeverSource
from sqlalchemy import select

from tests.conftest import make_user


def test_html_to_text_and_normalisers():
    assert html_to_text("<p>Hello&nbsp;<b>world</b></p><script>x()</script><br>Bye") == "Hello world\n\nBye"
    assert html_to_text("&lt;p&gt;Escaped &amp;amp; fine&lt;/p&gt;") == "Escaped & fine"
    assert normalize_employment_type("Full-Time") == "full-time"
    assert normalize_employment_type("Summer Internship") == "internship"
    assert normalize_employment_type(None) is None
    assert looks_remote("Remote - India") and not looks_remote("Bengaluru")
    assert parse_dt(1735689600000).year == 2025 and parse_dt("2026-10-01T00:00:00Z").tzinfo is not None
    assert parse_dt("garbage") is None


def test_job_posting_defaults():
    p = JobPosting(
        source="greenhouse", source_job_id="", company="", title=" Backend Dev ", apply_url="https://x.y/j/1", location="Remote"
    )
    assert p.source_job_id and p.company == "greenhouse" and p.title == "Backend Dev" and p.remote is True
    twin = JobPosting(
        source="greenhouse", source_job_id="", company="", title="Backend Dev", apply_url="https://x.y/j/1", location="Remote"
    )
    assert p.content_hash == twin.content_hash and p.source_job_id == twin.source_job_id


def _posting(i: int, **kw) -> JobPosting:
    base = dict(
        source="test",
        source_job_id=str(i),
        company="Acme",
        title=f"Python Backend Engineer {i}",
        apply_url=f"https://acme.test/{i}",
        description="We need Python, FastAPI, PostgreSQL and AWS experience.",
        location="Bengaluru, India",
        posted_at=datetime.now(UTC),
    )
    base.update(kw)
    return JobPosting(**base)


async def test_upsert_and_stale(session):
    counts = await upsert_postings(session, [_posting(1), _posting(2), _posting(2)])
    assert counts == {"new": 2, "updated": 0, "unchanged": 0}
    counts = await upsert_postings(session, [_posting(1), _posting(2, description="changed text")])
    assert counts == {"new": 0, "updated": 1, "unchanged": 1}
    jobs = (await session.scalars(select(m.Job).order_by(m.Job.source_job_id))).all()
    assert len(jobs) == 2 and all(j.embedding is not None and len(j.embedding) == 64 for j in jobs)
    jobs[0].last_seen_at = datetime.now(UTC) - timedelta(days=30)
    await session.flush()
    assert await deactivate_stale(session, sources={"test"}) == 1
    await session.refresh(jobs[0])
    assert jobs[0].is_active is False


GH_JOBS = {
    "jobs": [
        {
            "id": 11,
            "title": "SDE",
            "absolute_url": "https://boards.greenhouse.io/acme/jobs/11",
            "location": {"name": "Remote"},
            "content": "&lt;p&gt;Build things&lt;/p&gt;",
            "updated_at": "2026-10-01T00:00:00Z",
            "metadata": [{"name": "Employment Type", "value": "Full-time"}],
        }
    ]
}
LEVER_JOBS = [
    {
        "id": "abc",
        "text": "Data Engineer",
        "categories": {"location": "Pune", "commitment": "Internship"},
        "descriptionPlain": "Pipelines",
        "lists": [{"text": "Requirements", "content": "<li>SQL</li>"}],
        "hostedUrl": "https://jobs.lever.co/acme/abc",
        "applyUrl": "https://jobs.lever.co/acme/abc/apply",
        "createdAt": 1735689600000,
        "workplaceType": "onsite",
    }
]


@respx.mock
async def test_greenhouse_and_lever_adapters():
    respx.get("https://boards-api.greenhouse.io/v1/boards/acme").mock(return_value=httpx.Response(200, json={"name": "Acme Inc"}))
    respx.get("https://boards-api.greenhouse.io/v1/boards/acme/jobs").mock(return_value=httpx.Response(200, json=GH_JOBS))
    respx.get("https://api.lever.co/v0/postings/acme").mock(return_value=httpx.Response(200, json=LEVER_JOBS))
    async with httpx.AsyncClient() as client:
        gh = await GreenhouseSource().fetch(client, "acme")
        lv = await LeverSource().fetch(client, "acme")
    assert gh[0].company == "Acme Inc" and gh[0].title == "SDE" and gh[0].remote is True
    assert gh[0].employment_type == "full-time" and gh[0].description == "Build things"
    assert lv[0].title == "Data Engineer" and lv[0].employment_type == "internship" and lv[0].posted_at.year == 2025
    assert "SQL" in lv[0].description and lv[0].apply_url.endswith("/apply")


@respx.mock
async def test_run_ingest_reports_errors_and_saves(monkeypatch, session):
    monkeypatch.setenv("JOB_BOARDS", "greenhouse:acme,lever:missing,nosuch:x")
    from app.config import reset_settings_cache

    reset_settings_cache()
    try:
        respx.get("https://boards-api.greenhouse.io/v1/boards/acme").mock(
            return_value=httpx.Response(200, json={"name": "Acme Inc"})
        )
        respx.get("https://boards-api.greenhouse.io/v1/boards/acme/jobs").mock(return_value=httpx.Response(200, json=GH_JOBS))
        respx.get("https://api.lever.co/v0/postings/missing").mock(return_value=httpx.Response(404))
        report = await run_ingest()
    finally:
        monkeypatch.delenv("JOB_BOARDS")
        reset_settings_cache()
    assert report["boards"]["greenhouse:acme"]["new"] == 1
    assert any("board not found" in e for e in report["errors"]) and any("unknown board provider" in e for e in report["errors"])
    assert (await session.scalar(select(m.Job.title))) == "SDE"


async def test_matching_ranks_relevant_jobs(session):
    user = await make_user(
        session,
        headline="Python backend developer",
        skills=["python", "fastapi", "postgresql"],
        location="Bengaluru",
        preferences={
            "titles": ["backend engineer"],
            "locations": ["Bengaluru"],
            "remote": "any",
            "exclude_companies": ["Evil Corp"],
        },
    )
    await upsert_postings(
        session,
        [
            _posting(1),
            _posting(2, company="Evil Corp"),
            _posting(3, title="Senior Accountant", description="Accounting, tax, audit, Excel.", location="Mumbai"),
            _posting(4, title="Python Developer", location="Remote", remote=True),
        ],
    )
    await session.commit()
    result = await refresh_matches_for_user(user.id, limit=10)
    assert result["status"] == "ok"
    rows = (
        await session.execute(
            select(m.JobMatch, m.Job)
            .join(m.Job, m.Job.id == m.JobMatch.job_id)
            .where(m.JobMatch.user_id == user.id)
            .order_by(m.JobMatch.score.desc())
        )
    ).all()
    titles = [job.title for _, job in rows]
    assert "Evil Corp" not in {job.company for _, job in rows}
    assert titles[0].startswith("Python") and titles[-1] == "Senior Accountant"
    best = rows[0][0]
    assert best.explanation["location_ok"] is True and any("python" in s.lower() for s in best.explanation["strengths"])
    accountant = rows[-1][0]
    assert accountant.explanation["location_ok"] is False and float(accountant.score) < float(best.score)


async def test_matching_without_profile_text(session):
    user = await make_user(session)
    assert (await refresh_matches_for_user(user.id))["status"] == "no_profile"


async def test_jobs_api_and_mark_applied(client, auth, session):
    await upsert_postings(session, [_posting(1), _posting(2, title="Frontend Engineer", description="React, TypeScript")])
    await session.commit()
    found = await client.get("/api/v1/jobs", params={"query": "frontend"}, headers=auth)
    assert found.status_code == 200 and found.json()["total"] == 1
    job_id = found.json()["items"][0]["id"]
    detail = await client.get(f"/api/v1/jobs/{job_id}", headers=auth)
    assert detail.json()["company"] == "Acme" and "React" in detail.json()["description"]
    applied = await client.patch(f"/api/v1/matches/{job_id}", headers=auth, json={"status": "applied"})
    assert applied.status_code == 200 and applied.json()["status"] == "applied"
    again = await client.patch(f"/api/v1/matches/{job_id}", headers=auth, json={"status": "applied"})
    assert again.status_code == 200
    apps = await client.get("/api/v1/applications", headers=auth)
    assert apps.json()["total"] == 1, "marking applied twice does not duplicate the tracker entry"
    item = apps.json()["items"][0]
    assert item["status"] == "applied" and item["next_follow_up_at"] and item["applied_at"]
    stats = await client.get("/api/v1/applications/stats", headers=auth)
    assert stats.json()["by_status"] == {"applied": 1} and stats.json()["applied_last_7_days"] == 1
    sources = await client.get("/api/v1/jobs/sources", headers=auth)
    assert "greenhouse" in sources.json()["board_providers"]


async def test_tracker_api_flow(client, auth):
    created = await client.post(
        "/api/v1/applications", headers=auth, json={"company": "Initech", "title": "SRE", "status": "applied"}
    )
    assert created.status_code == 201
    app_id = created.json()["id"]
    interview = await client.post(
        f"/api/v1/applications/{app_id}/interviews",
        headers=auth,
        json={
            "scheduled_at": (datetime.now(UTC) + timedelta(days=2)).isoformat(),
            "kind": "video",
            "location": "https://meet.test/x",
        },
    )
    assert interview.status_code == 201
    app = (await client.get(f"/api/v1/applications/{app_id}", headers=auth)).json()
    assert app["status"] == "interview"
    events = (await client.get(f"/api/v1/applications/{app_id}/events", headers=auth)).json()
    assert [e["to_status"] for e in events] == ["planned", "applied", "interview"]
    assert len((await client.get("/api/v1/interviews", headers=auth)).json()) == 1
    rejected = await client.patch(f"/api/v1/applications/{app_id}", headers=auth, json={"status": "rejected", "note": "no fit"})
    assert rejected.json()["status"] == "rejected" and rejected.json()["next_follow_up_at"] is None
    missing = await client.post("/api/v1/applications", headers=auth, json={"status": "planned"})
    assert missing.status_code == 400


async def test_matches_refresh_uses_llm_explanations(client, auth, session, inline_tasks):
    set_llm(
        FakeLLM(
            json_handler=lambda prompt, schema: {
                "summary": "Strong Python fit.",
                "strengths": ["Python"],
                "gaps": ["No AWS"],
                "recommended": True,
            }
        )
    )
    await client.patch("/api/v1/me/profile", headers=auth, json={"headline": "Python developer", "skills": ["python"]})
    await upsert_postings(session, [_posting(1)])
    await session.commit()
    assert (await client.post("/api/v1/matches/refresh", headers=auth)).status_code == 202
    matches = await client.get("/api/v1/matches", headers=auth)
    assert matches.status_code == 200 and len(matches.json()) == 1
    expl = matches.json()[0]["explanation"]
    assert expl["summary"] == "Strong Python fit." and "No AWS" in expl["gaps"]
    skip = await client.patch(f"/api/v1/matches/{matches.json()[0]['job']['id']}", headers=auth, json={"status": "skipped"})
    assert skip.status_code == 200
    assert (await client.get("/api/v1/matches", headers=auth)).json() == [], "skipped matches are hidden by default"
