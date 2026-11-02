import re

def score_job(profile_skills: list[str], headline: str | None, job_title: str, description: str | None, location: str | None, preferred_locations: list[str] | None = None) -> dict:
    """Deterministic explainable baseline matcher; replace/augment with an evaluated model later."""
    text = f"{job_title} {description or ''}".lower()
    skills = {s.strip().lower() for s in profile_skills if s and s.strip()}
    matched = sorted(skill for skill in skills if re.search(r"(?<![a-z0-9])" + re.escape(skill) + r"(?![a-z0-9])", text))
    skill_score = min(70.0, 70.0 * len(matched) / max(1, min(len(skills), 8))) if skills else 0.0
    headline_terms = {t for t in re.findall(r"[a-z0-9+#.]+", (headline or "").lower()) if len(t) > 2}
    title_terms = set(re.findall(r"[a-z0-9+#.]+", job_title.lower()))
    title_score = min(20.0, 20.0 * len(headline_terms & title_terms) / max(1, min(len(headline_terms), 4))) if headline_terms else 0.0
    preferred = [p.lower() for p in (preferred_locations or []) if p]
    location_match = bool(location and (not preferred or any(p in location.lower() or p in {"remote", "india"} for p in preferred)))
    location_score = 10.0 if location_match else 0.0
    total = round(min(100.0, skill_score + title_score + location_score), 1)
    return {"score": total, "matched_skills": matched, "location_match": location_match, "method": "explainable_baseline_v1"}
