from __future__ import annotations
import asyncio,base64
from email.message import EmailMessage
import asyncpg,httpx
from app.approvals import digest
from app.oauth import gmail_access_token
from app.whatsapp import send_text_message
async def init_connection(c):
    import json
    await c.set_type_codec("json",encoder=json.dumps,decoder=json.loads,schema="pg_catalog")
    await c.set_type_codec("jsonb",encoder=json.dumps,decoder=json.loads,schema="pg_catalog")
async def send_gmail(pool,user_id,payload):
    if payload.get("attachments"): raise RuntimeError("Email attachments are not enabled yet; create a new approval without attachments")
    token=await gmail_access_token(pool,user_id)
    msg=EmailMessage(); msg["To"]=payload["recipient"]; msg["Subject"]=payload.get("subject") or "(no subject)"; msg.set_content(payload["message"])
    raw=base64.urlsafe_b64encode(msg.as_bytes()).decode().rstrip("=")
    async with httpx.AsyncClient(timeout=30) as client:
        response=await client.post("https://gmail.googleapis.com/gmail/v1/users/me/messages/send",headers={"Authorization":f"Bearer {token}"},json={"raw":raw})
    if response.is_error: raise RuntimeError(f"Gmail send failed with HTTP {response.status_code}")
    return str(response.json().get("id",""))
async def process_one(pool):
    async with pool.acquire() as conn:
        async with conn.transaction():
            job=await conn.fetchrow("""SELECT q.id,q.approval_id,q.user_id,a.action_type,a.payload,a.content_hash FROM external_action_jobs q
              JOIN action_approvals a ON a.id=q.approval_id WHERE q.status='pending' AND q.available_at<=now()
              AND a.status='approved' AND a.executed_at IS NULL ORDER BY q.created_at FOR UPDATE OF q SKIP LOCKED LIMIT 1""")
            if job is None: return False
            await conn.execute("UPDATE external_action_jobs SET status='processing',attempts=attempts+1,updated_at=now() WHERE id=$1",job["id"])
    try:
        payload=job["payload"]
        if digest(payload)!=job["content_hash"]: raise RuntimeError("Approved payload hash mismatch; refusing to send")
        if job["action_type"]=="email.send": provider_id=await send_gmail(pool,job["user_id"],payload)
        elif job["action_type"]=="whatsapp.message":
            result=await send_text_message(payload["recipient"],payload["message"]); provider_id=str((result.get("messages") or [{}])[0].get("id",""))
        else: raise RuntimeError("This action type has no authorized provider adapter")
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("UPDATE action_approvals SET executed_at=now() WHERE id=$1 AND status='approved' AND executed_at IS NULL",job["approval_id"])
                await conn.execute("UPDATE external_action_jobs SET status='done',provider_message_id=$1,last_error=NULL,updated_at=now() WHERE id=$2",provider_id,job["id"])
                await conn.execute("INSERT INTO audit_events(user_id,event_type,resource_id,details) VALUES($1,'action.sent',$2,$3)",job["user_id"],job["approval_id"],{"provider_message_id":provider_id})
    except Exception as exc:
        async with pool.acquire() as conn:
            await conn.execute("UPDATE external_action_jobs SET status=CASE WHEN attempts>=3 THEN 'failed' ELSE 'blocked' END,last_error=$1,updated_at=now() WHERE id=$2",str(exc)[:500],job["id"])
            await conn.execute("INSERT INTO audit_events(user_id,event_type,resource_id,details) VALUES($1,'action.send_failed',$2,$3)",job["user_id"],job["approval_id"],{"error":str(exc)[:300]})
    return True
async def run_worker(dsn):
    pool=await asyncpg.create_pool(dsn,min_size=1,max_size=5,init=init_connection)
    try:
        while True:
            if not await process_one(pool): await asyncio.sleep(2)
    finally: await pool.close()
