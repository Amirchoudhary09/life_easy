from __future__ import annotations
from datetime import datetime,timezone
import os
import asyncpg,httpx

def parse_date(value):
    if not value: return None
    try:
        if isinstance(value,(int,float)): return datetime.fromtimestamp(value/1000,timezone.utc)
        parsed=datetime.fromisoformat(str(value).replace("Z","+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (ValueError,TypeError,OverflowError): return None

def normalize_greenhouse(item,board):
    location=(item.get("location") or {}).get("name") or "Not specified"
    return {"source":"greenhouse","source_job_id":str(item.get("id") or ""),"company":(item.get("company_name") or board)[:200],"title":(item.get("title") or "Untitled role")[:300],"location":location[:300],"description":(item.get("content") or "")[:50000],"apply_url":item.get("absolute_url") or "","source_url":item.get("absolute_url") or "","posted_at":parse_date(item.get("updated_at")),"is_remote":"remote" in location.lower()}

def normalize_lever(item,site):
    categories=item.get("categories") or {}; location=str(categories.get("location") or "Not specified")
    return {"source":"lever","source_job_id":str(item.get("id") or ""),"company":(item.get("company") or site)[:200],"title":(item.get("text") or "Untitled role")[:300],"location":location[:300],"description":(item.get("descriptionPlain") or item.get("description") or "")[:50000],"apply_url":item.get("hostedUrl") or item.get("applyUrl") or "","source_url":item.get("hostedUrl") or "","posted_at":parse_date(item.get("createdAt")),"is_remote":"remote" in location.lower()}

async def ingest_configured_boards(pool:asyncpg.Pool):
    greenhouse=[x.strip() for x in os.getenv("GREENHOUSE_BOARD_TOKENS","").split(",") if x.strip()]
    lever=[x.strip() for x in os.getenv("LEVER_SITE_NAMES","").split(",") if x.strip()]
    boards=[("greenhouse",x) for x in greenhouse]+[("lever",x) for x in lever]
    if not boards: return {"status":"not_configured","boards":0,"jobs":0}
    total=inserted=updated=0
    async with httpx.AsyncClient(timeout=35,follow_redirects=True,headers={"User-Agent":"LifeEasyJobIndexer/1.0"}) as client:
        for source,key in boards:
            run_id=await pool.fetchval("INSERT INTO job_source_runs(source,board_key,status) VALUES($1,$2,'running') RETURNING id",source,key)
            try:
                url=(f"https://boards-api.greenhouse.io/v1/boards/{key}/jobs?content=true" if source=="greenhouse" else f"https://api.lever.co/v0/postings/{key}?mode=json")
                response=await client.get(url); response.raise_for_status(); data=response.json()
                items=data.get("jobs",[]) if source=="greenhouse" else data
                normalized=[normalize_greenhouse(x,key) if source=="greenhouse" else normalize_lever(x,key) for x in items]
                board_inserted=board_updated=0
                for job in normalized:
                    if not job["source_job_id"] or not job["apply_url"]: continue
                    row=await pool.fetchrow("""INSERT INTO jobs(source,source_job_id,company,title,location,description,apply_url,source_url,posted_at,is_remote,source_checked_at)
                      VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,now())
                      ON CONFLICT(source,source_job_id) DO UPDATE SET company=EXCLUDED.company,title=EXCLUDED.title,location=EXCLUDED.location,
                      description=EXCLUDED.description,apply_url=EXCLUDED.apply_url,source_url=EXCLUDED.source_url,posted_at=EXCLUDED.posted_at,
                      is_remote=EXCLUDED.is_remote,source_checked_at=now()
                      RETURNING (xmax=0) AS inserted""",job["source"],job["source_job_id"],job["company"],job["title"],job["location"],job["description"],job["apply_url"],job["source_url"],job["posted_at"],job["is_remote"])
                    if row["inserted"]: board_inserted+=1
                    else: board_updated+=1
                total+=len(normalized); inserted+=board_inserted; updated+=board_updated
                await pool.execute("UPDATE job_source_runs SET fetched_count=$1,inserted_count=$2,updated_count=$3,status='success',finished_at=now() WHERE id=$4",len(normalized),board_inserted,board_updated,run_id)
            except Exception as exc:
                await pool.execute("UPDATE job_source_runs SET status='failed',error_message=$1,finished_at=now() WHERE id=$2",str(exc)[:500],run_id)
    return {"status":"completed","boards":len(boards),"jobs":total,"inserted":inserted,"updated":updated}
