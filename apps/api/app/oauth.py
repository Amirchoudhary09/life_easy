from __future__ import annotations
import hashlib,os,secrets
from datetime import datetime,timedelta,timezone
from urllib.parse import urlencode
import asyncpg,httpx
from cryptography.fernet import Fernet
from fastapi import APIRouter,Depends,HTTPException,Query
from fastapi.responses import RedirectResponse
from app.auth import current_user
from app.db import get_db
router=APIRouter(prefix="/api/v1/integrations",tags=["Integrations"])
SCOPES=["https://www.googleapis.com/auth/gmail.send","openid","email"]
def cipher():
    key=os.getenv("TOKEN_ENCRYPTION_KEY","")
    if not key: raise RuntimeError("TOKEN_ENCRYPTION_KEY is not configured")
    try: return Fernet(key.encode())
    except Exception: raise RuntimeError("TOKEN_ENCRYPTION_KEY must be a valid Fernet key")
@router.delete("/{provider}")
async def disconnect_provider(provider:str,user=Depends(current_user),db:asyncpg.Pool=Depends(get_db)):
    if provider not in {"gmail"}: raise HTTPException(status_code=400,detail="Unsupported provider")
    await db.execute("UPDATE provider_connections SET status='disconnected',access_token_encrypted=NULL,refresh_token_encrypted=NULL,updated_at=now() WHERE user_id=$1 AND provider=$2",user["id"],provider)
    return {"status":"disconnected","provider":provider}

@router.get("")
async def list_integrations(user=Depends(current_user),db:asyncpg.Pool=Depends(get_db)):
    rows=await db.fetch("SELECT provider,account_email,status,scopes,created_at,updated_at FROM provider_connections WHERE user_id=$1 ORDER BY provider",user["id"])
    return {"integrations":[dict(r) for r in rows]}
@router.get("/gmail/connect")
async def gmail_connect(user=Depends(current_user),db:asyncpg.Pool=Depends(get_db)):
    client_id=os.getenv("GOOGLE_CLIENT_ID",""); redirect=os.getenv("GOOGLE_REDIRECT_URI","")
    if not client_id or not redirect: raise HTTPException(status_code=503,detail="Google OAuth credentials are not configured yet")
    state=secrets.token_urlsafe(32)
    await db.execute("INSERT INTO oauth_states(user_id,provider,state_hash,expires_at) VALUES($1,'gmail',$2,now()+interval '10 minutes')",user["id"],hashlib.sha256(state.encode()).hexdigest())
    params={"client_id":client_id,"redirect_uri":redirect,"response_type":"code","scope":" ".join(SCOPES),"access_type":"offline","prompt":"consent","include_granted_scopes":"true","state":state}
    return {"authorization_url":"https://accounts.google.com/o/oauth2/v2/auth?"+urlencode(params)}
@router.get("/gmail/callback")
async def gmail_callback(code:str=Query(...),state:str=Query(...),db:asyncpg.Pool=Depends(get_db)):
    digest=hashlib.sha256(state.encode()).hexdigest()
    async with db.acquire() as conn:
        async with conn.transaction():
            row=await conn.fetchrow("SELECT id,user_id FROM oauth_states WHERE provider='gmail' AND state_hash=$1 AND expires_at>now() AND consumed_at IS NULL FOR UPDATE",digest)
            if row is None: raise HTTPException(status_code=400,detail="OAuth state is invalid or expired")
            await conn.execute("UPDATE oauth_states SET consumed_at=now() WHERE id=$1",row["id"])
    client_id=os.getenv("GOOGLE_CLIENT_ID",""); secret=os.getenv("GOOGLE_CLIENT_SECRET",""); redirect=os.getenv("GOOGLE_REDIRECT_URI","")
    if not all((client_id,secret,redirect)): raise HTTPException(status_code=503,detail="Google OAuth credentials are not configured")
    async with httpx.AsyncClient(timeout=30) as client:
        token=await client.post("https://oauth2.googleapis.com/token",data={"code":code,"client_id":client_id,"client_secret":secret,"redirect_uri":redirect,"grant_type":"authorization_code"})
        if token.is_error: raise HTTPException(status_code=502,detail="Google OAuth token exchange failed")
        tokens=token.json()
        identity=await client.get("https://www.googleapis.com/oauth2/v2/userinfo",headers={"Authorization":f"Bearer {tokens['access_token']}"})
        if identity.is_error: raise HTTPException(status_code=502,detail="Could not read connected Google account")
        account=identity.json()
    f=cipher(); access=f.encrypt(tokens["access_token"].encode()).decode(); refresh=f.encrypt(tokens["refresh_token"].encode()).decode() if tokens.get("refresh_token") else None
    await db.execute("""INSERT INTO provider_connections(user_id,provider,provider_account_id,account_email,access_token_encrypted,refresh_token_encrypted,token_expires_at,scopes,status)
      VALUES($1,'gmail',$2,$3,$4,$5,now()+($6::int*interval '1 second'),$7,'connected')
      ON CONFLICT(user_id,provider,provider_account_id) DO UPDATE SET account_email=EXCLUDED.account_email,access_token_encrypted=EXCLUDED.access_token_encrypted,
      refresh_token_encrypted=COALESCE(EXCLUDED.refresh_token_encrypted,provider_connections.refresh_token_encrypted),token_expires_at=EXCLUDED.token_expires_at,
      scopes=EXCLUDED.scopes,status='connected',updated_at=now()""",row["user_id"],account.get("id") or account.get("email"),account.get("email"),access,refresh,int(tokens.get("expires_in",3600)),SCOPES)
    return RedirectResponse(os.getenv("FRONTEND_ORIGIN","http://localhost:3000")+"/dashboard?integration=gmail_connected",status_code=303)
async def gmail_access_token(db:asyncpg.Pool,user_id):
    row=await db.fetchrow("SELECT id,access_token_encrypted,refresh_token_encrypted,token_expires_at FROM provider_connections WHERE user_id=$1 AND provider='gmail' AND status='connected' ORDER BY updated_at DESC LIMIT 1",user_id)
    if row is None: raise RuntimeError("Gmail account is not connected")
    f=cipher(); access=f.decrypt(row["access_token_encrypted"].encode()).decode()
    if row["token_expires_at"] and row["token_expires_at"]>datetime.now(timezone.utc)+timedelta(seconds=90): return access
    if not row["refresh_token_encrypted"]: raise RuntimeError("Gmail connection needs to be re-authorized")
    refresh=f.decrypt(row["refresh_token_encrypted"].encode()).decode()
    async with httpx.AsyncClient(timeout=30) as client:
        response=await client.post("https://oauth2.googleapis.com/token",data={"client_id":os.getenv("GOOGLE_CLIENT_ID",""),"client_secret":os.getenv("GOOGLE_CLIENT_SECRET",""),"refresh_token":refresh,"grant_type":"refresh_token"})
    if response.is_error: raise RuntimeError("Gmail token refresh failed")
    data=response.json(); encrypted=f.encrypt(data["access_token"].encode()).decode()
    await db.execute("UPDATE provider_connections SET access_token_encrypted=$1,token_expires_at=now()+($2::int*interval '1 second'),updated_at=now() WHERE id=$3",encrypted,int(data.get("expires_in",3600)),row["id"])
    return data["access_token"]
