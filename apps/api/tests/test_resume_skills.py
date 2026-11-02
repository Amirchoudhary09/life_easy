from app.resumes import detect_skills
def test_resume_skill_detection_is_case_insensitive():
    assert detect_skills("Built APIs with Python, FastAPI, PostgreSQL and Docker") == ["docker","fastapi","postgresql","python"]
