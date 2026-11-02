from __future__ import annotations
from uuid import UUID
import asyncpg
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,Field
from app.auth import current_user
from app.db import get_db
router=APIRouter(prefix="/api/v1/applications",tags=["Applications"])
STATUSES={"planned","applied","assessment","interview","offer","rejected","withdrawn"}
class ApplicationCreate(BaseModel):
    job_id:UUID|None=None
    company:str=Field(min_length=1,max_length=200)
    role:str=Field(min_length=1,max_length=300)
    job_url:str|None=Field(default=None,max_length=2000)
    status:str="planned"
    notes:str|None=Field(default=None,max_length=5000)
class ApplicationUpdate(BaseModel):
    status:str|None=None
    notes:str|None=Field(default=None,max_length=5000)
@router.get("")
async def list_applications(user=Depends(current_user),db:asyncpg.Pool=Depends(get_db)):
    rows=await db.fetch("""SELECT a.id,a.job_id,a.status,a.applied_at,a.notes,a.metadata,a.created_at,
      COALESCE(j.company,a.metadata->>'company') AS company,COALESCE(j.title,a.metadata->>'role') AS role,
      COALESCE(j.apply_url,a.metadata->>'job_url') AS job_url
      FROM applications a LEFT JOIN jobs j ON j.id=a.job_id WHERE a.user_id=$1 ORDER BY a.created_at DESC LIMIT 200""",user["id"])
    return {"applications":[dict(r) for r in rows]}
@router.post("",status_code=201)
async def create_application(body:ApplicationCreate,user=Depends(current_user),db:asyncpg.Pool=Depends(get_db)):
    if body.status not in STATUSES: raise HTTPException(status_code=422,detail="Invalid application status")
    if body.job_id and not await db.fetchval("SELECT 1 FROM jobs WHERE id=$1",body.job_id): raise HTTPException(status_code=404,detail="Job not found")
    row=await db.fetchrow("""INSERT INTO applications(user_id,job_id,status,notes,metadata,applied_at)
      VALUES($1,$2,$3,$4,$5,CASE WHEN $3='applied' THEN now() ELSE NULL END)
      RETURNING id,job_id,status,applied_at,notes,metadata,created_at""",user["id"],body.job_id,body.status,body.notes,{"company":body.company,"role":body.role,"job_url":body.job_url})
    return {"application":dict(row)}
@router.patch("/{application_id}")
async def update_application(application_id:UUID,body:ApplicationUpdate,user=Depends(current_user),db:asyncpg.Pool=Depends(get_db)):
    if body.status is not None and body.status not in STATUSES: raise HTTPException(status_code=422,detail="Invalid application status")
    row=await db.fetchrow("SELECT id,notes,status FROM applications WHERE id=$1 AND user_id=$2",application_id,user["id"])
    if row is None: raise HTTPException(status_code=404,detail="Application not found")
    updated=await db.fetchrow("""UPDATE applications SET status=COALESCE($1,status),notes=COALESCE($2,notes),
      applied_at=CASE WHEN $1='applied' AND applied_at IS NULL THEN now() ELSE applied_at END
      WHERE id=$3 AND user_id=$4 RETURNING id,job_id,status,applied_at,notes,metadata,created_at""",body.status,body.notes,application_id,user["id"])
    return {"application":dict(updated)}
@router.delete("/{application_id}",status_code=204)
async def delete_application(application_id:UUID,user=Depends(current_user),db:asyncpg.Pool=Depends(get_db)):
    result=await db.execute("DELETE FROM applications WHERE id=$1 AND user_id=$2",application_id,user["id"])
    if result.endswith(" 0"): raise HTTPException(status_code=404,detail="Application not found")
