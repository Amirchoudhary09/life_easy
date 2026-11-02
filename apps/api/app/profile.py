import asyncpg
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from app.auth import current_user
from app.db import get_db

router = APIRouter(prefix="/api/v1/profile", tags=["Profile"])

class ProfileBody(BaseModel):
    headline: str | None = Field(default=None, max_length=180)
    location: str | None = Field(default=None, max_length=120)
    experience_years: float | None = Field(default=None, ge=0, le=60)
    skills: list[str] = Field(default_factory=list, max_length=100)
    preferences: dict = Field(default_factory=dict)

@router.get("")
async def get_profile(user=Depends(current_user), db: asyncpg.Pool = Depends(get_db)):
    row = await db.fetchrow("SELECT user_id,headline,location,experience_years,skills,preferences,updated_at,resume_object_key FROM profiles WHERE user_id=$1", user["id"])
    if row is None:
        return {"profile": None, "resume_uploaded": False}
    result = dict(row)
    result["resume_uploaded"] = bool(result.pop("resume_object_key"))
    return {"profile": result}

@router.put("")
async def save_profile(body: ProfileBody, user=Depends(current_user), db: asyncpg.Pool = Depends(get_db)):
    row = await db.fetchrow("""
      INSERT INTO profiles(user_id,headline,location,experience_years,skills,preferences,updated_at)
      VALUES($1,$2,$3,$4,$5::jsonb,$6::jsonb,now())
      ON CONFLICT(user_id) DO UPDATE SET headline=EXCLUDED.headline,location=EXCLUDED.location,
      experience_years=EXCLUDED.experience_years,skills=EXCLUDED.skills,preferences=EXCLUDED.preferences,updated_at=now()
      RETURNING user_id,headline,location,experience_years,skills,preferences,updated_at
    """, user["id"], body.headline, body.location, body.experience_years, body.skills, body.preferences)
    return {"profile": dict(row)}
