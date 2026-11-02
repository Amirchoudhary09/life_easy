import os,secrets
from datetime import datetime,timedelta,timezone
from uuid import UUID
import asyncpg,jwt
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
def jwt_secret():
    secret=os.getenv("JWT_SECRET","")
    if len(secret)<32: raise HTTPException(status_code=503,detail="JWT_SECRET must be set to at least 32 characters")
    return secret
def token_for(user_id:UUID):
    now=datetime.now(timezone.utc)
    return jwt.encode({"sub":str(user_id),"iat":now,"exp":now+timedelta(hours=12),"iss":"life-easy"},jwt_secret(),algorithm="HS256")
def set_session(response:Response,user_id:UUID):
    token=token_for(user_id); csrf=secrets.token_urlsafe(32)
    secure=os.getenv("ENVIRONMENT","development").lower()=="production"
    same_site="none" if secure else "lax"
    response.set_cookie("life_easy_access",token,httponly=True,secure=secure,samesite=same_site,max_age=43200,path="/")
    response.set_cookie("life_easy_csrf",csrf,httponly=False,secure=secure,samesite=same_site,max_age=43200,path="/")
    return csrf
async def current_user(request:Request,credentials:HTTPAuthorizationCredentials|None=Depends(bearer),db:asyncpg.Pool=Depends(get_db)):
    token=credentials.credentials if credentials else request.cookies.get("life_easy_access")
    if not token: raise HTTPException(status_code=401,detail="Authentication required")
    try:
        payload=jwt.decode(token,jwt_secret(),algorithms=["HS256"],issuer="life-easy",options={"require":["sub","iat","exp","iss"]})
        user_id=UUID(payload["sub"])
    except (jwt.InvalidTokenError,ValueError,KeyError):
        raise HTTPException(status_code=401,detail="Invalid or expired session")
    user=await db.fetchrow("SELECT id,email,display_name,email_verified,phone_verified FROM app_users WHERE id=$1",user_id)
    if user is None: raise HTTPException(status_code=401,detail="Account not found")
    return user
@router.post("/register",status_code=201)
async def register(body:RegisterBody,response:Response,db:asyncpg.Pool=Depends(get_db)):
    jwt_secret()
    try:
        row=await db.fetchrow("INSERT INTO app_users(email,display_name,password_hash) VALUES($1,$2,$3) RETURNING id,email,display_name,email_verified",str(body.email).lower().strip(),body.display_name.strip(),hasher.hash(body.password))
    except asyncpg.UniqueViolationError: raise HTTPException(status_code=409,detail="Email is already registered")
    csrf=set_session(response,row["id"])
    return {"user":dict(row),"csrf_token":csrf,"token_type":"cookie","expires_in":43200,"email_verification":"required"}
@router.post("/login")
async def login(body:LoginBody,response:Response,db:asyncpg.Pool=Depends(get_db)):
    jwt_secret()
    row=await db.fetchrow("SELECT id,email,display_name,email_verified,password_hash FROM app_users WHERE email=$1",str(body.email).lower().strip())
    if row is None or not row["password_hash"] or not hasher.verify(body.password,row["password_hash"]):
        raise HTTPException(status_code=401,detail="Invalid email or password")
    csrf=set_session(response,row["id"])
    return {"user":{"id":str(row["id"]),"email":row["email"],"display_name":row["display_name"],"email_verified":row["email_verified"]},"csrf_token":csrf,"token_type":"cookie","expires_in":43200}
@router.post("/logout")
async def logout(response:Response):
    response.delete_cookie("life_easy_access",path="/")
    response.delete_cookie("life_easy_csrf",path="/")
    return {"status":"logged_out"}
@router.get("/me")
async def me(user=Depends(current_user)):
    return {"user":{"id":str(user["id"]),"email":user["email"],"display_name":user["display_name"],"email_verified":user["email_verified"],"phone_verified":user["phone_verified"]}}
