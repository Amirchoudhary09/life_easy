import asyncpg
from fastapi import HTTPException, Request

async def get_db(request: Request) -> asyncpg.Pool:
    pool = getattr(request.app.state, "db", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="Database is not configured")
    return pool
