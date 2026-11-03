"""Fixed-window rate limiting. Redis when configured, in-process memory otherwise."""

from __future__ import annotations

import time
from collections import defaultdict
from collections.abc import Callable

from fastapi import Depends, HTTPException, Request

from app.config import get_settings


class MemoryLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, list[float]] = defaultdict(list)

    async def hit(self, key: str, limit: int, window_seconds: int) -> bool:
        now = time.monotonic()
        bucket = self._hits[key]
        cutoff = now - window_seconds
        while bucket and bucket[0] < cutoff:
            bucket.pop(0)
        if len(bucket) >= limit:
            return False
        bucket.append(now)
        return True

    def reset(self) -> None:
        self._hits.clear()


class RedisLimiter:
    def __init__(self, url: str) -> None:
        import redis.asyncio as redis

        self._redis = redis.from_url(url)

    async def hit(self, key: str, limit: int, window_seconds: int) -> bool:
        window = int(time.time() // window_seconds)
        redis_key = f"rl:{key}:{window}"
        count = await self._redis.incr(redis_key)
        if count == 1:
            await self._redis.expire(redis_key, window_seconds)
        return int(count) <= limit


_limiter: MemoryLimiter | RedisLimiter | None = None


def get_limiter() -> MemoryLimiter | RedisLimiter:
    global _limiter
    if _limiter is None:
        url = get_settings().redis_url
        _limiter = RedisLimiter(url) if url else MemoryLimiter()
    return _limiter


def reset_limiter() -> None:
    global _limiter
    _limiter = None


def client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "?")
    return ip


def rate_limit(scope: str, limit: int | None = None, window_seconds: int = 60) -> Callable:
    """Dependency factory: `Depends(rate_limit("login", 10))`."""

    async def _dep(request: Request, limiter=Depends(get_limiter)) -> None:  # type: ignore[no-untyped-def]
        max_hits = limit or get_settings().rate_limit_per_minute
        key = f"{scope}:{client_key(request)}"
        if not await limiter.hit(key, max_hits, window_seconds):
            raise HTTPException(status_code=429, detail="Too many requests, slow down")

    return _dep
