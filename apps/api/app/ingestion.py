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

def number(value):
    if value is None: return None
    try: return float(value)
    except (ValueError,TypeError): return None

def normalize_greenhouse(item,board):
    location=(item.get("location") or {}).get("name") or "Not specified"
    return {"source":"greenhouse","source_job_id":str(item.get("id") or ""),"company":(item.get("company_name") or board.replace("-"," ").title())[:200],"title":(item.get("title") or "Untitled role")[:300],"location":location[:300],"description":(item.get("content") or "")[:50000],"apply_url":item.get("absolute_url") or "","source_url":item.get("absolute_url") or "","posted_at":parse_date(item.get("updated_at")),"is_remote":"remote" in location.lower(),"employment_type":None,"salary_min":None,"salary_max":None,"salary_currency":None}

def normalize_lever(item,site):
    categories=item.get("categories") or {}; location=str(categories.get("location") or "Not specified")
    return {"source":"lever","source_job_id":str(item.get("id") or ""),"company":(item.get("company") or site.replace("-"," ").title())[:200],"title":(item.get("text") or "Untitled role")[:300],"location":location[:300],"description":(item.get("descriptionPlain") or item.get("description") or "")[:50000],"apply_url":item.get("hostedUrl") or item.get("applyUrl") or "","source_url":item.get("hostedUrl") or "","posted_at":parse_date(item.get("createdAt")),"is_remote":"remote" in location.lower(),"employment_type":None,"salary_min":None,"salary_max":None,"salary_currency":None}

def normalize_jobicy(item):
    url=item.get("url") or item.get("applyUrl") or ""
    return {"source":"jobicy","source_job_id":str(item.get("id") or ""),"company":str(item.get("companyName") or "Unknown company")[:200],"title":str(item.get("jobTitle") or "Untitled role")[:300],"location":str(item.get("jobGeo") or "Remote / not specified")[:300],"description":str(item.get("jobDescription") or item.get("jobExcerpt") or "")[:50000],"apply_url":url,"source_url":url,"posted_at":parse_date(item.get("pubDate")),"is_remote":True,"employment_type":str(item.get("jobType") or "")[:100] or None,"salary_min":number(item.get("salaryMin")),"salary_max":number(item.get("salaryMax")),"salary_currency":str(item.get("salaryCurrency") or "")[:8] or None}

def normalize_remoteok(item):
    url=item.get("url") or item.get("apply_url") or ""
    return {"source":"remoteok","source_job_id":str(item.get("id") or item.get("slug") or ""),"company":str(item.get("company") or "Unknown company")[:200],"title":str(item.get("position") or "Untitled role")[:300],"location":str(item.get("location") or "Remote")[:300],"description":str(item.get("description") or "")[:50000],"apply_url":url,"source_url":url,"posted_at":parse_date(item.get("date")),"is_remote":True,"employment_type":None,"salary_min":number(item.get("salary_min")),"salary_max":number(item.get("salary_max")),"salary_currency":"USD" if item.get("salary_min") or item.get("salary_max") else None}

async def fetch_jobicy(client):
    jobs=[]; cursor=None
    for _ in range(3):
        params={"count":200,"geo":"apac","industry":"engineering"}
        if cursor: params["cursor"]=cursor
        response=await client.get("https://jobicy.com/api/jobs",params=params); response.raise_for_status()
        data=response.json(); jobs.extend(data.get("jobs",[]) or [])
        cursor=data.get("nextCursor")
        if not cursor: break
    return [normalize_jobicy(x) for x in jobs]

async def fetch_remoteok(client):
    response=await client.get("https://remoteok.com/api",headers={"Accept":"application/json"})
    response.raise_for_status()
    data=response.json()
    jobs=[x for x in (data if isinstance(data,list) else []) if isinstance(x,dict) and x.get("position") and x.get("id")]
    return [normalize_remoteok(x) for x in jobs]

async def ingest_configured_boards(pool:asyncpg.Pool):
    greenhouse=[x.strip() for x in os.getenv("GREENHOUSE_BOARD_TOKENS","").split(",") if x.strip()]
    lever=[x.strip() for x in os.getenv("LEVER_SITE_NAMES","").split(",") if x.strip()]
    sources=[("jobicy","public-apac"),("remoteok","public")]
    sources += [("greenhouse",x) for x in greenhouse]+[("lever",x) for x in lever]
    total=inserted=updated=0
    async with httpx.AsyncClient(timeout=45,follow_redirects=True,headers={"User-Agent":"LifeEasyJobIndexer/1.0 (+https://lifeeasy.app)"}) as client:
        for source,key in sources:
            run_id=await pool.fetchval("INSERT INTO job_source_runs(source,board_key,status) VALUES($1,$2,'running') RETURNING id",source,key)
            try:
                if source=="jobicy":
                    normalized=await fetch_jobicy(client)
                elif source=="remoteok":
                    normalized=await fetch_remoteok(client)
                else:
                    url=(f"https://boards-api.greenhouse.io/v1/boards/{key}/jobs?content=true" if source=="greenhouse" else f"https://api.lever.co/v0/postings/{key}?mode=json")
                    response=await client.get(url); response.raise_for_status(); data=response.json()
                    items=data.get("jobs",[]) if source=="greenhouse" else data
                    normalized=[normalize_greenhouse(x,key) if source=="greenhouse" else normalize_lever(x,key) for x in items]
                board_inserted=board_updated=0
                for job in normalized:
                    if not job["source_job_id"] or not job["apply_url"]: continue
                    row=await pool.fetchrow("""INSERT INTO jobs(source,source_job_id,company,title,location,description,apply_url,source_url,posted_at,is_remote,employment_type,salary_min,salary_max,salary_currency,source_checked_at)
                      VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,now())
                      ON CONFLICT(source,source_job_id) DO UPDATE SET company=EXCLUDED.company,title=EXCLUDED.title,location=EXCLUDED.location,
                      description=EXCLUDED.description,apply_url=EXCLUDED.apply_url,source_url=EXCLUDED.source_url,posted_at=EXCLUDED.posted_at,
                      is_remote=EXCLUDED.is_remote,employment_type=EXCLUDED.employment_type,salary_min=EXCLUDED.salary_min,salary_max=EXCLUDED.salary_max,
                      salary_currency=EXCLUDED.salary_currency,source_checked_at=now()
                      RETURNING (xmax=0) AS inserted""",job["source"],job["source_job_id"],job["company"],job["title"],job["location"],job["description"],job["apply_url"],job["source_url"],job["posted_at"],job["is_remote"],job["employment_type"],job["salary_min"],job["salary_max"],job["salary_currency"])
                    if row["inserted"]: board_inserted+=1
                    else: board_updated+=1
                total+=len(normalized); inserted+=board_inserted; updated+=board_updated
                await pool.execute("UPDATE job_source_runs SET fetched_count=$1,inserted_count=$2,updated_count=$3,status='success',finished_at=now() WHERE id=$4",len(normalized),board_inserted,board_updated,run_id)
            except Exception as exc:
                await pool.execute("UPDATE job_source_runs SET status='failed',error_message=$1,finished_at=now() WHERE id=$2",str(exc)[:500],run_id)
    return {"status":"completed","boards":len(sources),"jobs":total,"inserted":inserted,"updated":updated}
