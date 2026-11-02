from app.ingestion import normalize_greenhouse,normalize_lever,parse_date
def test_greenhouse_normalization():
    job=normalize_greenhouse({"id":42,"title":"Backend Engineer","location":{"name":"Remote - India"},"content":"Python","absolute_url":"https://boards.greenhouse.io/acme/jobs/42","updated_at":"2026-10-31T10:00:00Z"},"acme")
    assert job["source"]=="greenhouse" and job["source_job_id"]=="42" and job["is_remote"]
def test_lever_millisecond_timestamp():
    job=normalize_lever({"id":"abc","text":"Software Engineer","categories":{"location":"Noida"},"descriptionPlain":"Build APIs","hostedUrl":"https://jobs.lever.co/acme/abc","createdAt":1793430000000},"acme")
    assert job["source"]=="lever" and job["posted_at"] is not None
def test_invalid_date_is_safe():
    assert parse_date("not-a-date") is None
