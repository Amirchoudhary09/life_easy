from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings import get_embeddings, nearest_memories
from app.db import models as m


async def remember(session: AsyncSession, user_id: uuid.UUID, *, content: str, memory_type: str = "fact") -> m.MemoryItem:
    content = content.strip()[:2000]
    vec = (await get_embeddings().embed([content]))[0]
    item = m.MemoryItem(user_id=user_id, memory_type=memory_type[:40], content=content, embedding=vec)
    session.add(item)
    await session.flush()
    return item


async def recall(session: AsyncSession, user_id: uuid.UUID, query: str, *, limit: int = 6) -> list[str]:
    if not query.strip():
        return []
    vec = (await get_embeddings().embed([query[:2000]]))[0]
    items = await nearest_memories(session, user_id, vec, limit=limit)
    return [i.content for i in items]
