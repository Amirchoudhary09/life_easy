import os
from datetime import datetime, timedelta, timezone
from uuid import UUID
import asyncpg
import jwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr, Field
from pwdlib import PasswordHash
from app.db import get_db

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])
bearer = HTTPBearer(auto_error=False)
hasher = PasswordHash.recommended()

class RegisterBody(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    display_name: str = Field(min_length=1, max_length=100)

class LoginBody(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

def token_for(user_id: UUID) -> str:
    secret = os.getenv("JWT_SECRET", "")
    if len(secret) < 32:
        raise HTTPException(status_code=503, detail="JWT_SECRET must be set to at least 32 characters")
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": str(user_id), "iat": now, "exp": now + timedelta(hours=12), "iss": "life-easy"}, secret, algorithm="HS256")

async def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer), db: asyncpg.Pool = Depends(get_db)):
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Authentication required")
    secret = os.getenv("JWT_SECRET", "")
    if len(secret) < 32:
        raise HTTPException(status_code=503, detail="Authentication is not configured")
    try:
        payload = jwt.decode(credentials.credentials, secret, algorithms=["HS256"], issuer="life-easy", options={"require": ["sub", "iat", "exp", "iss"]})
        user_id = UUID(payload["sub"])
    except (jwt.InvalidTokenError, ValueError, KeyError):
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = await db.fetchrow("SELECT id,email,display_name,email_verified FROM app_users WHERE id=$1", user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Account not found")
    return user

@router.post("/register", status_code=201)
async def register(body: RegisterBody, db: asyncpg.Pool = Depends(get_db)):
    try:
        row = await db.fetchrow(
            "INSERT INTO app_users(email,display_name,password_hash) VALUES($1,$2,$3) RETURNING id,email,display_name,email_verified",
            str(body.email).lower().strip(), body.display_name.strip(), hasher.hash(body.password))
    except asyncpg.UniqueViolationError:
        raise HTTPException(status_code=409, detail="Email is already registered")
    return {"user": dict(row), "access_token": token_for(row["id"]), "token_type": "bearer", "expires_in": 43200, "email_verification": "not_configured"}

@router.post("/login")
async def login(body: LoginBody, db: asyncpg.Pool = Depends(get_db)):
    row = await db.fetchrow("SELECT id,email,display_name,email_verified,password_hash FROM app_users WHERE email=$1", str(body.email).lower().strip())
    if row is None or not hasher.verify(body.password, row["password_hash"] or ""):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return {"user": {"id": str(row["id"]), "email": row["email"], "display_name": row["display_name"], "email_verified": row["email_verified"]}, "access_token": token_for(row["id"]), "token_type": "bearer", "expires_in": 43200}

@router.get("/me")
async def me(user=Depends(current_user)):
    return {"user": {"id": str(user["id"]), "email": user["email"], "display_name": user["display_name"], "email_verified": user["email_verified"]}}
