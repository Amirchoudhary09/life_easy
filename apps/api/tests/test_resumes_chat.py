from __future__ import annotations

from app.ai.llm import FakeLLM, set_llm
from app.jobs.ingest import upsert_postings
from app.jobs.sources.base import JobPosting
from app.resumes.parser import extract_text

from tests.conftest import register


def _llm(prompt: str, schema: dict) -> dict:
    props = schema.get("properties", {})
    if "experience" in props:  # resume parse
        return {
            "headline": "Backend Developer",
            "skills": ["Python", "FastAPI", "python "],
            "experience": [],
            "years_experience": 3,
        }
    if "markdown" in props:  # tailoring
        return {
            "markdown": "# Amir\nPython, FastAPI",
            "ats": {"matched_keywords": ["python"], "missing_keywords": ["aws"], "score": 70},
        }
    return {}


def test_extract_text_plain_and_docx():
    assert extract_text(b"Line 1\r\n\r\n\r\nLine 2", "text/plain", "cv.txt") == "Line 1\n\nLine 2"
    import io

    from docx import Document

    buf = io.BytesIO()
    doc = Document()
    doc.add_paragraph("Python developer")
    doc.save(buf)
    assert "Python developer" in extract_text(buf.getvalue(), "application/octet-stream", "cv.docx")


async def test_upload_parse_tailor(client, auth, session, inline_tasks):
    set_llm(FakeLLM(json_handler=_llm))
    up = await client.post(
        "/api/v1/resumes", headers=auth, files={"file": ("cv.txt", b"Amir - Python, FastAPI, 3 years", "text/plain")}
    )
    assert up.status_code == 201 and up.json()["is_primary"] is True
    rid = up.json()["id"]
    detail = (await client.get(f"/api/v1/resumes/{rid}", headers=auth)).json()
    assert detail["has_text"] and detail["parsed"]["skills"] == ["Python", "FastAPI"]
    profile = (await client.get("/api/v1/me/profile", headers=auth)).json()
    assert profile["headline"] == "Backend Developer" and profile["experience_years"] == 3.0
    download = await client.get(f"/api/v1/resumes/{rid}/download", headers=auth)
    assert download.content == b"Amir - Python, FastAPI, 3 years"

    await upsert_postings(
        session,
        [
            JobPosting(
                source="t",
                source_job_id="1",
                company="Acme",
                title="Python Dev",
                apply_url="https://acme.example.com/1",
                description="Python and AWS",
            )
        ],
    )
    await session.commit()
    job_id = (await client.get("/api/v1/jobs", headers=auth)).json()["items"][0]["id"]
    tailored = await client.post("/api/v1/resumes/tailor", headers=auth, json={"job_id": job_id})
    assert tailored.status_code == 200, tailored.text
    assert tailored.json()["ats"]["missing_keywords"] == ["aws"] and tailored.json()["resume"]["tailored_for_job_id"] == job_id
    assert len((await client.get("/api/v1/resumes", headers=auth)).json()) == 2


async def test_upload_rejects_bad_files(client, auth):
    big = await client.post(
        "/api/v1/resumes", headers=auth, files={"file": ("cv.txt", b"x" * (5 * 1024 * 1024 + 1), "text/plain")}
    )
    assert big.status_code == 400
    exe = await client.post("/api/v1/resumes", headers=auth, files={"file": ("tool.exe", b"MZ", "application/x-msdownload")})
    assert exe.status_code == 400


async def test_resume_isolation(client, auth):
    up = await client.post("/api/v1/resumes", headers=auth, files={"file": ("cv.txt", b"secret cv", "text/plain")})
    other = await register(client, "other@example.com")
    assert (await client.get(f"/api/v1/resumes/{up.json()['id']}/download", headers=other)).status_code == 404


async def test_web_chat(client, auth):
    resp = await client.post("/api/v1/chat/messages", headers=auth, json={"text": "hi there"})
    assert resp.status_code == 200 and "[fake-llm]" in resp.json()["reply"] and resp.json()["approvals"] == []
    history = (await client.get("/api/v1/chat/messages", headers=auth)).json()
    assert [h["role"] for h in history] == ["user", "assistant"]


async def test_llm_daily_limit(client, auth, monkeypatch):
    monkeypatch.setenv("MAX_LLM_CALLS_PER_USER_PER_DAY", "1")
    from app.config import reset_settings_cache

    reset_settings_cache()
    try:
        assert (await client.post("/api/v1/chat/messages", headers=auth, json={"text": "one"})).status_code == 200
        second = await client.post("/api/v1/chat/messages", headers=auth, json={"text": "two"})
        assert second.status_code == 429 and second.json()["error"]["code"] == "limit_exceeded"
    finally:
        monkeypatch.delenv("MAX_LLM_CALLS_PER_USER_PER_DAY")
        reset_settings_cache()
