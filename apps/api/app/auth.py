import os,secrets
from datetime import datetime,timedelta,timezone
from uuid import UUID
import asyncpg,jwt,httpx
from fastapi import APIRouter,Depends,HTTPException,Request,Response
from fastapi.security import HTTPAuthorizationCredentials,HTTPBearer
from pydantic import BaseModel,EmailStr,Field
from pwdlib import PasswordHash
from app.db import get_db
router=APIRouter(prefix="/api/v1/auth",tags=["Authentication"])
bearer=HTTPBearer(auto_error=False)
hasher=PasswordHash.recommended()
class RegisterBody(BaseModel):
    email:EmailStr
    password:str=Field(min_length=12,max_length=128)
    display_name:str=Field(min_length=1,max_length=100)
class LoginBody(BaseModel):
    email:EmailStr
    password:str=Field(min_length=1,max_length=128)
class PhoneLoginSend(BaseModel):
    phone_e164:str=Field(pattern=r"^\+[1-9]\d{7,14}$")
class PhoneLoginVerify(PhoneLoginSend):
    code:str=Field(pattern=r"^\d{6}$")
def jwt_secret():
    secret=os.getenv("JWT_SECRET","")
    if len(secret)<32: raise HTTPException(status_code=503,detail="JWT_SECRET must be set to at least 32 characters")
    return secret
def token_for(user_id:UUID):
    now=datetime.now(timezone.utc)
    return jwt.encode({"sub":str(user_id),"iat":now,"exp":now+timedelta(hours=12),"iss":"life-easy"},jwt_secret(),algorithm="HS256")
def set_session(response:Response,user_id:UUID):
    token=token_for(user_id); csrf=secrets.token_urlsafe(32)
    secure=os.getenv("ENVIRONMENT","development").lower()=="production"; same_site="none" if secure else "lax"
    response.set_cookie("life_easy_access",token,httponly=True,secure=secure,samesite=same_site,max_age=43200,path="/")
    response.set_cookie("life_easy_csrf",csrf,httponly=False,secure=secure,samesite=same_site,max_age=43200,path="/")
    return csrf
async def current_user(request:Request,credentials:HTTPAuthorizationCredentials|None=Depends(bearer),db:asyncpg.Pool=Depends(get_db)):
    token=credentials.credentials if credentials else request.cookies.get("life_easy_access")
    if not token: raise HTTPException(status_code=401,detail="Authentication required")
    try:
        payload=jwt.decode(token,jwt_secret(),algorithms=["HS256"],issuer="life-easy",options={"require":["sub","iat","exp","iss"]})
        user_id=UUID(payload["sub"])
    except (jwt.InvalidTokenError,ValueError,KeyError): raise HTTPException(status_code=401,detail="Invalid or expired session")
    user=await db.fetchrow("SELECT id,email,display_name,email_verified,phone_verified FROM app_users WHERE id=$1",user_id)
    if user is None: raise HTTPException(status_code=401,detail="Account not found")
    return user
@router.post("/register",status_code=201)
async def register(body:RegisterBody,response:Response,db:asyncpg.Pool=Depends(get_db)):
    jwt_secret()
    try: row=await db.fetchrow("INSERT INTO app_users(email,display_name,password_hash) VALUES($1,$2,$3) RETURNING id,email,display_name,email_verified",str(body.email).lower().strip(),body.display_name.strip(),hasher.hash(body.password))
    except asyncpg.UniqueViolationError: raise HTTPException(status_code=409,detail="Email is already registered")
    csrf=set_session(response,row["id"])
    return {"user":dict(row),"csrf_token":csrf,"token_type":"cookie","expires_in":43200,"email_verification":"required"}
@router.post("/login")
async def login(body:LoginBody,response:Response,db:asyncpg.Pool=Depends(get_db)):
    jwt_secret()
    row=await db.fetchrow("SELECT id,email,display_name,email_verified,password_hash FROM app_users WHERE email=$1",str(body.email).lower().strip())
    if row is None or not row["password_hash"] or not hasher.verify(body.password,row["password_hash"]): raise HTTPException(status_code=401,detail="Invalid email or password")
    csrf=set_session(response,row["id"])
    return {"user":{"id":str(row["id"]),"email":row["email"],"display_name":row["display_name"],"email_verified":row["email_verified"]},"csrf_token":csrf,"token_type":"cookie","expires_in":43200}
@router.post("/phone/send")
async def phone_login_send(body:PhoneLoginSend,db:asyncpg.Pool=Depends(get_db)):
    sid=os.getenv("TWILIO_ACCOUNT_SID",""); token=os.getenv("TWILIO_AUTH_TOKEN",""); service=os.getenv("TWILIO_VERIFY_SERVICE_SID","")
    if not all((sid,token,service)): raise HTTPException(status_code=503,detail="Phone OTP provider is not configured yet")
    recent=await db.fetchval("SELECT count(*) FROM otp_challenges WHERE target=$1 AND purpose='login' AND created_at>now()-interval '1 hour'",body.phone_e164)
    if recent>=3: raise HTTPException(status_code=429,detail="Too many OTP requests. Try again later.")
    user=await db.fetchrow("SELECT id FROM app_users WHERE phone_e164=$1 AND phone_verified=TRUE",body.phone_e164)
    if user is None: return {"status":"sent","message":"If this number belongs to a verified Life Easy account, a code has been sent."}
    async with httpx.AsyncClient(timeout=20) as client:
        result=await client.post(f"https://verify.twilio.com/v2/Services/{service}/Verifications",auth=(sid,token),data={"To":body.phone_e164,"Channel":"sms"})
    if result.is_error: raise HTTPException(status_code=502,detail="Could not send phone OTP")
    await db.execute("INSERT INTO otp_challenges(user_id,channel,target,purpose,code_hash,expires_at) VALUES($1,'sms',$2,'login','twilio',now()+interval '10 minutes')",user["id"],body.phone_e164)
    return {"status":"sent","message":"If this number belongs to a verified Life Easy account, a code has been sent.","expires_in":600}
@router.post("/phone/verify")
async def phone_login_verify(body:PhoneLoginVerify,response:Response,db:asyncpg.Pool=Depends(get_db)):
    sid=os.getenv("TWILIO_ACCOUNT_SID",""); token=os.getenv("TWILIO_AUTH_TOKEN",""); service=os.getenv("TWILIO_VERIFY_SERVICE_SID","")
    if not all((sid,token,service)): raise HTTPException(status_code=503,detail="Phone OTP provider is not configured yet")
    row=await db.fetchrow("SELECT id,user_id FROM otp_challenges WHERE target=$1 AND purpose='login' AND consumed_at IS NULL AND expires_at>now() ORDER BY created_at DESC LIMIT 1",body.phone_e164)
    if row is None: raise HTTPException(status_code=400,detail="OTP expired or not found")
    async with httpx.AsyncClient(timeout=20) as client:
        result=await client.post(f"https://verify.twilio.com/v2/Services/{service}/VerificationCheck",auth=(sid,token),data={"To":body.phone_e164,"Code":body.code})
    if result.is_error or result.json().get("status")!="approved": raise HTTPException(status_code=400,detail="Incorrect or expired OTP")
    user=await db.fetchrow("SELECT id,email,display_name,email_verified,phone_verified FROM app_users WHERE id=$1 AND phone_e164=$2 AND phone_verified=TRUE",row["user_id"],body.phone_e164)
    if user is None: raise HTTPException(status_code=401,detail="Phone number is not linked to an active verified account")
    await db.execute("UPDATE otp_challenges SET consumed_at=now() WHERE id=$1",row["id"])
    csrf=set_session(response,user["id"])
    return {"user":{"id":str(user["id"]),"email":user["email"],"display_name":user["display_name"],"email_verified":user["email_verified"]},"csrf_token":csrf,"token_type":"cookie","expires_in":43200}
@router.post("/logout")
async def logout(response:Response):
    response.delete_cookie("life_easy_access",path="/"); response.delete_cookie("life_easy_csrf",path="/")
    return {"status":"logged_out"}
@router.get("/me")
async def me(user=Depends(current_user)):
    return {"user":{"id":str(user["id"]),"email":user["email"],"display_name":user["display_name"],"email_verified":user["email_verified"],"phone_verified":user["phone_verified"]}}
