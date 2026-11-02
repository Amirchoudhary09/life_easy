from __future__ import annotations
import hashlib,hmac,os,secrets
from typing import Any
import asyncpg,httpx
from fastapi import APIRouter,Depends,HTTPException,Query,Request
from fastapi.responses import PlainTextResponse
from app.auth import current_user
from app.db import get_db
from app.feature_flags import feature_enabled
from app.assistant import generate_reply
router=APIRouter(prefix="/api/v1/webhooks/whatsapp",tags=["WhatsApp"])
VERIFY_TOKEN=os.getenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN","")
APP_SECRET=os.getenv("WHATSAPP_APP_SECRET","")
ACCESS_TOKEN=os.getenv("WHATSAPP_ACCESS_TOKEN","")
PHONE_NUMBER_ID=os.getenv("WHATSAPP_PHONE_NUMBER_ID","")
GRAPH_API_VERSION=os.getenv("WHATSAPP_GRAPH_API_VERSION","v22.0")
def valid_signature(raw,header):
    if not APP_SECRET or not header or not header.startswith("sha256="): return False
    expected="sha256="+hmac.new(APP_SECRET.encode(),raw,hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected,header)
def code_hash(code):
    pepper=os.getenv("OTP_PEPPER","") or os.getenv("JWT_SECRET","")
    return hmac.new(pepper.encode(),code.upper().encode(),hashlib.sha256).hexdigest()
@router.get("")
async def verify_webhook(hub_mode:str|None=Query(None,alias="hub.mode"),hub_verify_token:str|None=Query(None,alias="hub.verify_token"),hub_challenge:str|None=Query(None,alias="hub.challenge")):
    if not VERIFY_TOKEN: raise HTTPException(status_code=503,detail="WhatsApp webhook is not configured")
    if hub_mode=="subscribe" and hmac.compare_digest(hub_verify_token or "",VERIFY_TOKEN): return PlainTextResponse(hub_challenge or "")
    raise HTTPException(status_code=403,detail="Webhook verification failed")
@router.get("/status")
async def whatsapp_status(user=Depends(current_user),db:asyncpg.Pool=Depends(get_db)):
    row=await db.fetchrow("SELECT provider,provider_user_id,verified_at,is_active,created_at FROM channel_identities WHERE user_id=$1 AND provider='whatsapp' AND is_active=TRUE ORDER BY created_at DESC LIMIT 1",user["id"])
    return {"connected":row is not None,"identity":dict(row) if row else None}

@router.delete("/link")
async def disconnect_whatsapp(user=Depends(current_user),db:asyncpg.Pool=Depends(get_db)):
    await db.execute("UPDATE channel_identities SET is_active=FALSE WHERE user_id=$1 AND provider='whatsapp'",user["id"])
    await db.execute("UPDATE channel_link_tokens SET consumed_at=COALESCE(consumed_at,now()) WHERE user_id=$1 AND provider='whatsapp'",user["id"])
    return {"status":"disconnected"}

@router.post("/link-code")
async def create_link_code(user=Depends(current_user),db:asyncpg.Pool=Depends(get_db)):
    recent=await db.fetchval("SELECT count(*) FROM channel_link_tokens WHERE user_id=$1 AND provider='whatsapp' AND created_at>now()-interval '1 hour'",user["id"])
    if recent>=5: raise HTTPException(status_code=429,detail="Too many link codes generated. Try again later.")
    alphabet="ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    code="".join(secrets.choice(alphabet) for _ in range(8))
    pepper=os.getenv("OTP_PEPPER","") or os.getenv("JWT_SECRET","")
    if len(pepper)<32: raise HTTPException(status_code=503,detail="OTP_PEPPER or JWT_SECRET is not configured")
    await db.execute("INSERT INTO channel_link_tokens(user_id,provider,token_hash,expires_at) VALUES($1,'whatsapp',$2,now()+interval '10 minutes')",user["id"],code_hash(code))
    return {"code":code,"expires_in":600,"instruction":"Send LINK followed by this code to your Life Easy WhatsApp Business number."}
def extract_messages(payload:dict[str,Any])->list[dict]:
    result=[]
    for entry in payload.get("entry",[]):
        for change in entry.get("changes",[]):
            value=change.get("value",{})
            if change.get("field")=="messages" and (value.get("metadata",{}).get("phone_number_id")==PHONE_NUMBER_ID):
                for item in value.get("messages",[]) or []:
                    if item.get("type")=="text" and item.get("text",{}).get("body"):
                        result.append({"from":item.get("from",""),"id":item.get("id",""),"text":item["text"]["body"]})
    return result
async def send_text_message(recipient,text):
    if not all((ACCESS_TOKEN,PHONE_NUMBER_ID,GRAPH_API_VERSION)): raise RuntimeError("WhatsApp Cloud API credentials are not configured")
    if not recipient or not text.strip(): raise ValueError("recipient and message text are required")
    url=f"https://graph.facebook.com/{GRAPH_API_VERSION}/{PHONE_NUMBER_ID}/messages"
    async with httpx.AsyncClient(timeout=20) as client:
        response=await client.post(url,headers={"Authorization":f"Bearer {ACCESS_TOKEN}"},json={"messaging_product":"whatsapp","recipient_type":"individual","to":recipient,"type":"text","text":{"preview_url":False,"body":text}})
    if response.status_code>=500: raise httpx.HTTPStatusError(f"WhatsApp send status uncertain: HTTP {response.status_code}",request=response.request,response=response)
    if response.is_error: raise RuntimeError(f"WhatsApp send rejected with HTTP {response.status_code}")
    return response.json()
@router.post("")
async def receive_webhook(request:Request,db:asyncpg.Pool=Depends(get_db)):
    raw=await request.body()
    if not valid_signature(raw,request.headers.get("x-hub-signature-256")): raise HTTPException(status_code=401,detail="Invalid webhook signature")
    try: payload=await request.json()
    except Exception: raise HTTPException(status_code=400,detail="Invalid JSON payload")
    messages=extract_messages(payload if isinstance(payload,dict) else {})
    processed=0
    for item in messages:
        sender=item["from"]; text=item["text"].strip()
        if not sender or not item["id"]: continue
        if text.upper().startswith("LINK "):
            code=text[5:].strip().upper()
            async with db.acquire() as conn:
                async with conn.transaction():
                    link=await conn.fetchrow("SELECT id,user_id FROM channel_link_tokens WHERE provider='whatsapp' AND token_hash=$1 AND expires_at>now() AND consumed_at IS NULL FOR UPDATE",code_hash(code))
                    if link:
                        await conn.execute("INSERT INTO channel_identities(user_id,provider,provider_user_id,verified_at,is_active) VALUES($1,'whatsapp',$2,now(),TRUE) ON CONFLICT(provider,provider_user_id) DO UPDATE SET user_id=EXCLUDED.user_id,verified_at=now(),is_active=TRUE",link["user_id"],sender)
                        await conn.execute("UPDATE channel_link_tokens SET consumed_at=now() WHERE id=$1",link["id"])
                        processed+=1
            if link: await send_text_message(sender,"Your WhatsApp is now connected to Life Easy. You can ask me about jobs, resumes and career planning.")
            else: await send_text_message(sender,"That linking code is invalid or expired. Generate a new code from your Life Easy dashboard.")
            continue
        identity=await db.fetchrow("SELECT user_id FROM channel_identities WHERE provider='whatsapp' AND provider_user_id=$1 AND is_active=TRUE",sender)
        if identity is None: continue
        if not await feature_enabled(db,"whatsapp_assistant",True): continue
        cid=await db.fetchval("SELECT id FROM conversations WHERE user_id=$1 AND channel='whatsapp' AND channel_conversation_id=$2",identity["user_id"],sender)
        if cid is None: cid=await db.fetchval("INSERT INTO conversations(user_id,channel,channel_conversation_id) VALUES($1,'whatsapp',$2) RETURNING id",identity["user_id"],sender)
        exists=await db.fetchval("SELECT 1 FROM conversation_messages WHERE provider_message_id=$1",item["id"])
        if exists: continue
        try:
            answer=await generate_reply(db,identity["user_id"],cid,text,provider_message_id=item["id"])
            await send_text_message(sender,answer)
            processed+=1
        except Exception:
            # Acknowledge the provider event; internal failures are not exposed to the sender.
            continue
    return {"status":"accepted","message_events_received":len(messages),"processed":processed}
