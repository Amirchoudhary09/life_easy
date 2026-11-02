from app.matching import score_job


def test_skill_and_title_match_is_explainable():
    result = score_job(
        ["Python", "FastAPI", "PostgreSQL"],
        "Backend Software Engineer",
        "Backend Engineer",
        "Build APIs with Python and FastAPI",
        "Noida, India",
        ["Noida"],
    )
    assert result["score"] > 0
    assert result["matched_skills"] == ["fastapi", "python"]
    assert result["location_match"] is True


def test_empty_profile_does_not_invent_skill_matches():
    result = score_job([], None, "Software Engineer", "Build software", "Remote", ["Remote"])
    assert result["matched_skills"] == []
    assert result["score"] == 10.0
