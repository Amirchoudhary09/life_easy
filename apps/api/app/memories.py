from __future__ import annotations
from uuid import UUID
import asyncpg
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,Field
from app.auth import current_user
from app.db import get_db
router=APIRouter(prefix="/api/v1/memories",tags=["Memory"])
class MemoryBody(BaseModel):
    memory_key:str=Field(min_length=2,max_length=100,pattern=r"^[a-zA-Z0-9_.-]+$")
    memory_value:str=Field(min_length=1,max_length=2000)
@router.get("")
async def list_memories(user=Depends(current_user),db:asyncpg.Pool=Depends(get_db)):
    rows=await db.fetch("SELECT id,memory_key,memory_value,source,created_at,updated_at FROM user_memories WHERE user_id=$1 ORDER BY updated_at DESC",user["id"])
    return {"memories":[dict(x) for x in rows]}
@router.put("")
async def upsert_memory(body:MemoryBody,user=Depends(current_user),db:asyncpg.Pool=Depends(get_db)):
    row=await db.fetchrow("""INSERT INTO user_memories(user_id,memory_key,memory_value,source) VALUES($1,$2,$3,'user')
      ON CONFLICT(user_id,memory_key) DO UPDATE SET memory_value=EXCLUDED.memory_value,updated_at=now()
      RETURNING id,memory_key,memory_value,source,updated_at""",user["id"],body.memory_key,body.memory_value)
    return {"memory":dict(row)}
@router.delete("/{memory_id}",status_code=204)
async def delete_memory(memory_id:UUID,user=Depends(current_user),db:asyncpg.Pool=Depends(get_db)):
    result=await db.execute("DELETE FROM user_memories WHERE id=$1 AND user_id=$2",memory_id,user["id"])
    if result.endswith(" 0"): raise HTTPException(status_code=404,detail="Memory not found")
