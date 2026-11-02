from __future__ import annotations
import hashlib,hmac,os,secrets
from uuid import UUID
import asyncpg,httpx
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,Field
from app.auth import current_user
from app.db import get_db
router=APIRouter(prefix="/api/v1/verification",tags=["Verification"])
MAX_ATTEMPTS=5

def _secret():
    value=os.getenv("OTP_PEPPER","") or os.getenv("JWT_SECRET","")
    if len(value)<32: raise HTTPException(status_code=503,detail="OTP_PEPPER or JWT_SECRET must be configured")
    return value
def _hash(challenge_id:UUID,code:str):
    return hmac.new(_secret().encode(),f"{challenge_id}:{code}".encode(),hashlib.sha256).hexdigest()
async def _email(target:str,code:str):
    key=os.getenv("RESEND_API_KEY",""); sender=os.getenv("RESEND_FROM_EMAIL","")
    if not key or not sender: raise HTTPException(status_code=503,detail="Email OTP provider is not configured yet")
    async with httpx.AsyncClient(timeout=20) as c:
        r=await c.post("https://api.resend.com/emails",headers={"Authorization":f"Bearer {key}"},json={"from":sender,"to":[target],"subject":"Your Life Easy verification code","text":f"Your Life Easy code is {code}. It expires in 10 minutes. Do not share it."})
    if r.is_error: raise HTTPException(status_code=502,detail="Could not deliver verification email")
async def _sms_start(target:str):
    sid=os.getenv("TWILIO_ACCOUNT_SID",""); token=os.getenv("TWILIO_AUTH_TOKEN",""); service=os.getenv("TWILIO_VERIFY_SERVICE_SID","")
    if not all((sid,token,service)): raise HTTPException(status_code=503,detail="SMS OTP provider is not configured yet")
    async with httpx.AsyncClient(timeout=20) as c:
        r=await c.post(f"https://verify.twilio.com/v2/Services/{service}/Verifications",auth=(sid,token),data={"To":target,"Channel":"sms"})
    if r.is_error: raise HTTPException(status_code=502,detail="Could not start phone verification")
class CodeBody(BaseModel):
    code:str=Field(pattern=r"^\d{6}$")
class PhoneBody(BaseModel):
    phone_e164:str=Field(pattern=r"^\+[1-9]\d{7,14}$")

@router.post("/email/send")
async def send_email(user=Depends(current_user),db:asyncpg.Pool=Depends(get_db)):
    recent=await db.fetchval("SELECT count(*) FROM otp_challenges WHERE user_id=$1 AND channel='email' AND created_at>now()-interval '1 hour'",user["id"])
    if recent>=5: raise HTTPException(status_code=429,detail="Too many codes requested. Try again later.")
    code=f"{secrets.randbelow(1000000):06d}"
    cid=await db.fetchval("INSERT INTO otp_challenges(user_id,channel,target,purpose,code_hash,expires_at) VALUES($1,'email',$2,'verify_email','pending',now()+interval '10 minutes') RETURNING id",user["id"],user["email"])
    await db.execute("UPDATE otp_challenges SET code_hash=$1 WHERE id=$2",_hash(cid,code),cid)
    try: await _email(user["email"],code)
    except Exception:
        await db.execute("DELETE FROM otp_challenges WHERE id=$1",cid); raise
    return {"status":"sent","channel":"email","expires_in":600}

@router.post("/email/verify")
async def verify_email(body:CodeBody,user=Depends(current_user),db:asyncpg.Pool=Depends(get_db)):
    async with db.acquire() as conn:
        async with conn.transaction():
            row=await conn.fetchrow("SELECT id,code_hash,attempts FROM otp_challenges WHERE user_id=$1 AND channel='email' AND purpose='verify_email' AND consumed_at IS NULL AND expires_at>now() ORDER BY created_at DESC LIMIT 1 FOR UPDATE",user["id"])
            if row is None: raise HTTPException(status_code=400,detail="Code expired or not found")
            if row["attempts"]>=MAX_ATTEMPTS: raise HTTPException(status_code=429,detail="Too many incorrect attempts")
            if not hmac.compare_digest(_hash(row["id"],body.code),row["code_hash"]):
                await conn.execute("UPDATE otp_challenges SET attempts=attempts+1 WHERE id=$1",row["id"])
                raise HTTPException(status_code=400,detail="Incorrect verification code")
            await conn.execute("UPDATE otp_challenges SET consumed_at=now() WHERE id=$1",row["id"])
            await conn.execute("UPDATE app_users SET email_verified=TRUE,updated_at=now() WHERE id=$1",user["id"])
    return {"status":"verified","email_verified":True}

@router.post("/phone/send")
async def send_phone(body:PhoneBody,user=Depends(current_user),db:asyncpg.Pool=Depends(get_db)):
    recent=await db.fetchval("SELECT count(*) FROM otp_challenges WHERE user_id=$1 AND channel='sms' AND created_at>now()-interval '1 hour'",user["id"])
    if recent>=3: raise HTTPException(status_code=429,detail="Too many SMS requests. Try again later.")
    await _sms_start(body.phone_e164)
    cid=await db.fetchval("INSERT INTO otp_challenges(user_id,channel,target,purpose,code_hash,expires_at) VALUES($1,'sms',$2,'verify_phone','twilio',now()+interval '10 minutes') RETURNING id",user["id"],body.phone_e164)
    return {"status":"sent","challenge_id":str(cid),"expires_in":600}

@router.post("/phone/verify")
async def verify_phone(body:CodeBody,user=Depends(current_user),db:asyncpg.Pool=Depends(get_db)):
    row=await db.fetchrow("SELECT id,target FROM otp_challenges WHERE user_id=$1 AND channel='sms' AND purpose='verify_phone' AND consumed_at IS NULL AND expires_at>now() ORDER BY created_at DESC LIMIT 1",user["id"])
    if row is None: raise HTTPException(status_code=400,detail="Phone verification expired or not found")
    sid=os.getenv("TWILIO_ACCOUNT_SID",""); token=os.getenv("TWILIO_AUTH_TOKEN",""); service=os.getenv("TWILIO_VERIFY_SERVICE_SID","")
    async with httpx.AsyncClient(timeout=20) as c:
        r=await c.post(f"https://verify.twilio.com/v2/Services/{service}/VerificationCheck",auth=(sid,token),data={"To":row["target"],"Code":body.code})
    if r.is_error or r.json().get("status")!="approved": raise HTTPException(status_code=400,detail="Incorrect or expired phone verification code")
    try: await db.execute("UPDATE app_users SET phone_e164=$1,phone_verified=TRUE,updated_at=now() WHERE id=$2",row["target"],user["id"])
    except asyncpg.UniqueViolationError: raise HTTPException(status_code=409,detail="This phone number is already linked to another account")
    await db.execute("UPDATE otp_challenges SET consumed_at=now() WHERE id=$1",row["id"])
    return {"status":"verified","phone_verified":True}
