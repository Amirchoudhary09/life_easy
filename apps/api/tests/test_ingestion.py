from app.ingestion import normalize_greenhouse,normalize_lever,normalize_jobicy,normalize_remoteok,parse_date
def test_greenhouse_normalization():
    job=normalize_greenhouse({"id":42,"title":"Backend Engineer","location":{"name":"Remote - India"},"content":"Python","absolute_url":"https://boards.greenhouse.io/acme/jobs/42","updated_at":"2026-10-31T10:00:00Z"},"acme")
    assert job["source"]=="greenhouse" and job["source_job_id"]=="42" and job["is_remote"]
def test_lever_millisecond_timestamp():
    job=normalize_lever({"id":"abc","text":"Software Engineer","categories":{"location":"Noida"},"descriptionPlain":"Build APIs","hostedUrl":"https://jobs.lever.co/acme/abc","createdAt":1793430000000},"acme")
    assert job["source"]=="lever" and job["posted_at"] is not None
def test_jobicy_salary_and_source_link():
    job=normalize_jobicy({"id":123,"companyName":"Acme","jobTitle":"Python Engineer","jobGeo":"Asia","jobDescription":"Build systems","url":"https://jobicy.com/jobs/123","pubDate":"2026-10-30T12:00:00Z","salaryMin":80000,"salaryMax":100000,"salaryCurrency":"USD"})
    assert job["source"]=="jobicy" and job["salary_min"]==80000 and job["apply_url"]=="https://jobicy.com/jobs/123"
def test_remoteok_retains_attribution_url():
    job=normalize_remoteok({"id":"abc","company":"Acme","position":"SWE","location":"Worldwide","url":"https://remoteok.com/remote-jobs/abc","date":"2026-10-30T12:00:00Z"})
    assert job["source"]=="remoteok" and job["source_url"]==job["apply_url"]
def test_invalid_date_is_safe():
    assert parse_date("not-a-date") is None
