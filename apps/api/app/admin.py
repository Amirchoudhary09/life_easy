from __future__ import annotations
import os
from uuid import UUID
import asyncpg
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,Field
from app.auth import current_user
from app.db import get_db
from app.ingestion import ingest_configured_boards

router=APIRouter(prefix="/api/v1/admin",tags=["Admin and Developer"])

def is_allowlisted_admin(user)->bool:
    allowed={x.strip().lower() for x in os.getenv("ADMIN_EMAILS","").split(",") if x.strip()}
    return str(user["email"]).lower() in allowed

async def admin_user(user=Depends(current_user)):
    if user["role"]!="admin" and not is_allowlisted_admin(user):
        raise HTTPException(status_code=403,detail="Administrator access is not enabled for this account")
    return user

async def developer_user(user=Depends(current_user)):
    if user["role"] not in {"admin","developer"} and not is_allowlisted_admin(user):
        raise HTTPException(status_code=403,detail="Developer access is not enabled for this account")
    return user

class UserStatusBody(BaseModel):
    status:str=Field(pattern="^(active|suspended)$")
class UserRoleBody(BaseModel):
    role:str=Field(pattern="^(user|admin|developer)$")
class JobSourceBody(BaseModel):
    provider:str=Field(pattern="^(greenhouse|lever)$")
    board_key:str=Field(min_length=1,max_length=160,pattern="^[A-Za-z0-9_-]+$")
    active:bool=True
class FeatureFlagBody(BaseModel):
    enabled:bool
    description:str=Field(default="",max_length=500)

@router.get("/overview")
async def overview(user=Depends(developer_user),db:asyncpg.Pool=Depends(get_db)):
    row=await db.fetchrow("""SELECT
      (SELECT count(*) FROM app_users) AS users_total,
      (SELECT count(*) FROM app_users WHERE status='active') AS users_active,
      (SELECT count(*) FROM app_users WHERE created_at>now()-interval '7 days') AS users_new_7d,
      (SELECT count(*) FROM jobs) AS jobs_indexed,
      (SELECT count(*) FROM applications) AS applications_total,
      (SELECT count(*) FROM provider_connections WHERE status='connected') AS integrations_connected,
      (SELECT count(*) FROM action_approvals WHERE status='pending') AS approvals_pending,
      (SELECT count(*) FROM external_action_jobs WHERE status IN ('pending','processing')) AS deliveries_queued,
      (SELECT count(*) FROM external_action_jobs WHERE status='uncertain') AS deliveries_uncertain""")
    return {"metrics":dict(row),"database":"connected"}

@router.get("/users")
async def list_users(q:str|None=None,limit:int=Query(50,ge=1,le=100),offset:int=Query(0,ge=0),user=Depends(admin_user),db:asyncpg.Pool=Depends(get_db)):
    rows=await db.fetch("""SELECT u.id,u.email,u.display_name,u.role,u.status,u.email_verified,u.phone_verified,u.created_at,
      (SELECT count(*) FROM applications a WHERE a.user_id=u.id) AS applications_count,
      (SELECT count(*) FROM resume_documents r WHERE r.user_id=u.id) AS resumes_count
      FROM app_users u WHERE ($1::text IS NULL OR u.email ILIKE '%'||$1||'%' OR COALESCE(u.display_name,'') ILIKE '%'||$1||'%')
      ORDER BY u.created_at DESC LIMIT $2 OFFSET $3""",q,limit,offset)
    total=await db.fetchval("SELECT count(*) FROM app_users WHERE ($1::text IS NULL OR email ILIKE '%'||$1||'%' OR COALESCE(display_name,'') ILIKE '%'||$1||'%')",q)
    return {"users":[dict(x) for x in rows],"total":total,"limit":limit,"offset":offset}

@router.patch("/users/{user_id}/status")
async def set_user_status(user_id:UUID,body:UserStatusBody,actor=Depends(admin_user),db:asyncpg.Pool=Depends(get_db)):
    if str(actor["id"])==str(user_id) and body.status=="suspended": raise HTTPException(status_code=400,detail="You cannot suspend your own active admin session")
    target=await db.fetchrow("SELECT role,email FROM app_users WHERE id=$1",user_id)
    if target is None: raise HTTPException(status_code=404,detail="User not found")
    allowlist={x.strip().lower() for x in os.getenv("ADMIN_EMAILS","").split(",") if x.strip()}
    if body.status=="suspended" and (target["role"]=="admin" or target["email"].lower() in allowlist):
        admins=await db.fetchval("SELECT count(*) FROM app_users WHERE status='active' AND (role='admin' OR lower(email)=ANY($1::text[]))",sorted(allowlist))
        if admins<=1: raise HTTPException(status_code=409,detail="Cannot suspend the last active administrator")
    row=await db.fetchrow("UPDATE app_users SET status=$1,updated_at=now() WHERE id=$2 RETURNING id,email,status",body.status,user_id)
    await db.execute("INSERT INTO audit_events(user_id,event_type,resource_id,details) VALUES($1,'admin.user_status_changed',$2,$3)",actor["id"],user_id,{"status":body.status})
    return {"user":dict(row)}

@router.patch("/users/{user_id}/role")
async def set_user_role(user_id:UUID,body:UserRoleBody,actor=Depends(admin_user),db:asyncpg.Pool=Depends(get_db)):
    if str(actor["id"])==str(user_id) and body.role!="admin": raise HTTPException(status_code=400,detail="You cannot remove your own admin role")
    target=await db.fetchrow("SELECT role,email,email_verified,phone_verified FROM app_users WHERE id=$1",user_id)
    if target is None: raise HTTPException(status_code=404,detail="User not found")
    allowlist={x.strip().lower() for x in os.getenv("ADMIN_EMAILS","").split(",") if x.strip()}
    if body.role in {"admin","developer"} and not (target["email_verified"] or target["phone_verified"]):
        raise HTTPException(status_code=409,detail="Verify the user's email or phone before granting privileged access")
    if body.role!="admin" and (target["role"]=="admin" or target["email"].lower() in allowlist):
        admins=await db.fetchval("SELECT count(*) FROM app_users WHERE status='active' AND (role='admin' OR lower(email)=ANY($1::text[]))",sorted(allowlist))
        if admins<=1: raise HTTPException(status_code=409,detail="Cannot remove the last active administrator")
    row=await db.fetchrow("UPDATE app_users SET role=$1,updated_at=now() WHERE id=$2 RETURNING id,email,role",body.role,user_id)
    await db.execute("INSERT INTO audit_events(user_id,event_type,resource_id,details) VALUES($1,'admin.user_role_changed',$2,$3)",actor["id"],user_id,{"role":body.role})
    return {"user":dict(row)}

@router.get("/jobs")
async def list_jobs(q:str|None=None,limit:int=Query(50,ge=1,le=100),offset:int=Query(0,ge=0),user=Depends(developer_user),db:asyncpg.Pool=Depends(get_db)):
    rows=await db.fetch("""SELECT id,source,source_job_id,company,title,location,apply_url,posted_at,source_checked_at,is_remote
      FROM jobs WHERE ($1::text IS NULL OR title ILIKE '%'||$1||'%' OR company ILIKE '%'||$1||'%')
      ORDER BY source_checked_at DESC LIMIT $2 OFFSET $3""",q,limit,offset)
    return {"jobs":[dict(x) for x in rows]}

@router.get("/job-sources")
async def get_job_sources(user=Depends(developer_user),db:asyncpg.Pool=Depends(get_db)):
    rows=await db.fetch("SELECT id,provider,board_key,active,created_at,updated_at FROM admin_job_sources ORDER BY provider,board_key")
    runs=await db.fetch("SELECT source,board_key,status,fetched_count,inserted_count,updated_count,error_message,started_at,finished_at FROM job_source_runs ORDER BY started_at DESC LIMIT 20")
    return {"sources":[dict(x) for x in rows],"recent_runs":[dict(x) for x in runs]}

@router.post("/job-sources",status_code=201)
async def add_job_source(body:JobSourceBody,actor=Depends(admin_user),db:asyncpg.Pool=Depends(get_db)):
    row=await db.fetchrow("""INSERT INTO admin_job_sources(provider,board_key,active,created_by)
      VALUES($1,$2,$3,$4) ON CONFLICT(provider,board_key) DO UPDATE SET active=EXCLUDED.active,updated_at=now()
      RETURNING id,provider,board_key,active,created_at,updated_at""",body.provider,body.board_key,body.active,actor["id"])
    await db.execute("INSERT INTO audit_events(user_id,event_type,resource_id,details) VALUES($1,'admin.job_source_saved',$2,$3)",actor["id"],row["id"],{"provider":body.provider,"board_key":body.board_key})
    return {"source":dict(row)}

@router.patch("/job-sources/{source_id}")
async def toggle_job_source(source_id:UUID,active:bool,actor=Depends(admin_user),db:asyncpg.Pool=Depends(get_db)):
    row=await db.fetchrow("UPDATE admin_job_sources SET active=$1,updated_at=now() WHERE id=$2 RETURNING id,provider,board_key,active",active,source_id)
    if row is None: raise HTTPException(status_code=404,detail="Job source not found")
    await db.execute("INSERT INTO audit_events(user_id,event_type,resource_id,details) VALUES($1,'admin.job_source_toggled',$2,$3)",actor["id"],source_id,{"active":active})
    return {"source":dict(row)}

@router.delete("/job-sources/{source_id}")
async def delete_job_source(source_id:UUID,actor=Depends(admin_user),db:asyncpg.Pool=Depends(get_db)):
    row=await db.fetchrow("DELETE FROM admin_job_sources WHERE id=$1 RETURNING id,provider,board_key",source_id)
    if row is None: raise HTTPException(status_code=404,detail="Job source not found")
    await db.execute("INSERT INTO audit_events(user_id,event_type,resource_id,details) VALUES($1,'admin.job_source_deleted',$2,$3)",actor["id"],source_id,{"provider":row["provider"],"board_key":row["board_key"]})
    return {"deleted":True}

@router.get("/feature-flags")
async def get_feature_flags(user=Depends(developer_user),db:asyncpg.Pool=Depends(get_db)):
    rows=await db.fetch("SELECT flag_key,enabled,description,updated_at FROM feature_flags ORDER BY flag_key")
    return {"flags":[dict(x) for x in rows]}

@router.put("/feature-flags/{flag_key}")
async def set_feature_flag(flag_key:str,body:FeatureFlagBody,actor=Depends(admin_user),db:asyncpg.Pool=Depends(get_db)):
    if not flag_key.replace("_","").replace("-","").isalnum() or len(flag_key)>80: raise HTTPException(status_code=422,detail="Invalid feature flag key")
    row=await db.fetchrow("""INSERT INTO feature_flags(flag_key,enabled,description,updated_by)
      VALUES($1,$2,$3,$4) ON CONFLICT(flag_key) DO UPDATE SET enabled=EXCLUDED.enabled,description=EXCLUDED.description,updated_by=EXCLUDED.updated_by,updated_at=now()
      RETURNING flag_key,enabled,description,updated_at""",flag_key,body.enabled,body.description,actor["id"])
    await db.execute("INSERT INTO audit_events(user_id,event_type,resource_id,details) VALUES($1,'admin.feature_flag_changed',$2,$3)",actor["id"],None,{"flag_key":flag_key,"enabled":body.enabled})
    return {"flag":dict(row)}

@router.get("/audit")
async def audit_log(limit:int=Query(100,ge=1,le=250),user=Depends(developer_user),db:asyncpg.Pool=Depends(get_db)):
    rows=await db.fetch("""SELECT e.id,e.user_id,u.email,e.event_type,e.resource_id,e.details,e.created_at
      FROM audit_events e JOIN app_users u ON u.id=e.user_id ORDER BY e.created_at DESC LIMIT $1""",limit)
    return {"events":[dict(x) for x in rows]}

@router.get("/health")
async def developer_health(user=Depends(developer_user),db:asyncpg.Pool=Depends(get_db)):
    env=["JWT_SECRET","OTP_PEPPER","RESEND_API_KEY","TWILIO_VERIFY_SERVICE_SID","RESUME_BUCKET","OPENAI_API_KEY","TOKEN_ENCRYPTION_KEY","GOOGLE_CLIENT_ID","GOOGLE_CLIENT_SECRET","WHATSAPP_ACCESS_TOKEN","WHATSAPP_APP_SECRET"]
    configured={key:bool(os.getenv(key)) for key in env}
    counts=await db.fetchrow("SELECT count(*) FILTER(WHERE status='pending') AS pending,count(*) FILTER(WHERE status='processing') AS processing,count(*) FILTER(WHERE status='uncertain') AS uncertain,count(*) FILTER(WHERE status='failed') AS failed FROM external_action_jobs")
    heartbeat=await db.fetchrow("SELECT last_seen,metadata FROM worker_heartbeats WHERE service_name='background-worker'")
    return {"api":"healthy","database":"connected","worker":{"last_seen":heartbeat["last_seen"],"metadata":heartbeat["metadata"]} if heartbeat else {"last_seen":None,"status":"not_seen"},"providers":configured,"delivery_queue":dict(counts),"secrets_exposed":False}

@router.post("/jobs/ingest")
async def trigger_ingestion(user=Depends(developer_user),db:asyncpg.Pool=Depends(get_db)):
    return await ingest_configured_boards(db)
