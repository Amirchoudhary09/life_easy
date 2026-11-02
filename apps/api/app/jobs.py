from __future__ import annotations

import asyncpg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth import current_user
from app.db import get_db
from app.matching import score_job

router = APIRouter(prefix="/api/v1/jobs", tags=["Jobs"])

class SearchBody(BaseModel):
    query: str = Field(min_length=2, max_length=200)
    locations: list[str] = Field(default_factory=lambda: ["India"], max_length=10)
    limit: int = Field(default=20, ge=1, le=50)

@router.post("/search")
async def search_jobs(body: SearchBody, user=Depends(current_user), db: asyncpg.Pool=Depends(get_db)):
    profile = await db.fetchrow("SELECT headline,skills,preferences FROM profiles WHERE user_id=$1", user["id"])
    skills = list(profile["skills"] or []) if profile else []
    headline = profile["headline"] if profile else None
    patterns = [f"%{loc.strip()}%" for loc in body.locations if loc.strip()]
    rows = await db.fetch("""
      SELECT j.id,j.source,j.company,j.title,j.location,j.employment_type,j.experience_text,
             j.description,j.apply_url,j.posted_at,j.source_checked_at,m.status AS saved_status
      FROM jobs j LEFT JOIN job_matches m ON m.job_id=j.id AND m.user_id=$1
      WHERE (j.title ILIKE $2 OR j.company ILIKE $2 OR COALESCE(j.description,'') ILIKE $2)
        AND (cardinality($3::text[])=0 OR j.location ILIKE ANY($3::text[]))
        AND (j.expires_at IS NULL OR j.expires_at > now())
      ORDER BY j.posted_at DESC NULLS LAST, j.source_checked_at DESC
      LIMIT $4
    """, user["id"], f"%{body.query}%", patterns, body.limit)
    jobs=[]
    for row in rows:
        item=dict(row)
        item["match"]=score_job(skills,headline,item["title"],item["description"],item["location"],body.locations)
        item.pop("description",None)
        jobs.append(item)
    return {"status":"ok" if jobs else "no_indexed_jobs", "count":len(jobs), "jobs":jobs,
            "message":"Results are from indexed job sources. No live source adapters are connected yet." if not jobs else None}

@router.post("/{job_id}/save")
async def save_job(job_id: str,user=Depends(current_user),db: asyncpg.Pool=Depends(get_db)):
    try:
        row=await db.fetchrow("SELECT id FROM jobs WHERE id=$1::uuid",job_id)
    except asyncpg.DataError:
        raise HTTPException(status_code=404,detail="Job not found")
    if row is None:
        raise HTTPException(status_code=404,detail="Job not found")
    await db.execute("""
      INSERT INTO job_matches(user_id,job_id,status) VALUES($1,$2,'saved')
      ON CONFLICT(user_id,job_id) DO UPDATE SET status='saved'
    """,user["id"],row["id"])
    return {"job_id":job_id,"status":"saved"}

@router.get("/saved")
async def saved_jobs(user=Depends(current_user),db: asyncpg.Pool=Depends(get_db)):
    rows=await db.fetch("""
      SELECT j.id,j.company,j.title,j.location,j.apply_url,j.source,m.status,m.created_at
      FROM job_matches m JOIN jobs j ON j.id=m.job_id
      WHERE m.user_id=$1 AND m.status='saved'
      ORDER BY m.created_at DESC LIMIT 100
    """,user["id"])
    return {"jobs":[dict(row) for row in rows]}
