"""Embeddings: Voyage AI in production, a deterministic hashing embedder for dev/tests.

Nearest-neighbour search uses pgvector's cosine operator on Postgres and a
Python fallback on SQLite, so the same code runs on a laptop and in production.
"""

from __future__ import annotations

import hashlib
import math
import re
import uuid
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.errors import ProviderError
from app.db import models as m

_TOKEN = re.compile(r"[a-z0-9+#.]{2,}")


class Embeddings:
    name = "base"
    dim: int

    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError


class HashEmbeddings(Embeddings):
    """Bag-of-words hashed into `dim` buckets, L2-normalised. Similar text -> similar vectors."""

    name = "hash"

    def __init__(self, dim: int) -> None:
        self.dim = dim

    def _one(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for tok in _TOKEN.findall(text.lower()):
            h = int.from_bytes(hashlib.blake2b(tok.encode(), digest_size=8).digest(), "big")
            vec[h % self.dim] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._one(t) for t in texts]


class VoyageEmbeddings(Embeddings):
    name = "voyage"

    def __init__(self, api_key: str, model: str, dim: int) -> None:
        self._key = api_key
        self._model = model
        self.dim = dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        out: list[list[float]] = []
        async with httpx.AsyncClient(timeout=60.0) as client:
            for i in range(0, len(texts), 64):
                batch = [t[:16000] for t in texts[i : i + 64]]
                resp = await client.post(
                    "https://api.voyageai.com/v1/embeddings",
                    headers={"Authorization": f"Bearer {self._key}"},
                    json={"input": batch, "model": self._model, "input_type": "document"},
                )
                if resp.is_error:
                    raise ProviderError(f"embedding request failed with HTTP {resp.status_code}")
                data = resp.json()
                out.extend([d["embedding"] for d in data["data"]])
        return out


_emb: Embeddings | None = None


def get_embeddings() -> Embeddings:
    global _emb
    if _emb is None:
        s = get_settings()
        if s.embedding_provider == "voyage" and s.voyage_api_key:
            _emb = VoyageEmbeddings(s.voyage_api_key, s.voyage_model, s.embedding_dim)
        else:
            _emb = HashEmbeddings(s.embedding_dim)
    return _emb


def set_embeddings(emb: Embeddings | None) -> None:
    global _emb
    _emb = emb


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


async def nearest_jobs(
    session: AsyncSession,
    query: list[float],
    *,
    limit: int = 200,
    exclude_ids: set[uuid.UUID] | None = None,
) -> list[tuple[m.Job, float]]:
    """Active jobs ordered by cosine similarity to `query` (0..1)."""
    exclude_ids = exclude_ids or set()
    dialect = session.bind.dialect.name if session.bind is not None else "sqlite"
    if dialect == "postgresql":
        distance = m.Job.embedding.cosine_distance(query)  # type: ignore[attr-defined]
        stmt = (
            select(m.Job, distance.label("d"))
            .where(m.Job.is_active.is_(True), m.Job.embedding.is_not(None))
            .order_by(distance)
            .limit(limit + len(exclude_ids))
        )
        rows = (await session.execute(stmt)).all()
        return [(job, 1.0 - float(d)) for job, d in rows if job.id not in exclude_ids][:limit]
    rows = (await session.scalars(select(m.Job).where(m.Job.is_active.is_(True), m.Job.embedding.is_not(None)))).all()
    scored = [(job, cosine(query, job.embedding or [])) for job in rows if job.id not in exclude_ids]
    scored.sort(key=lambda t: t[1], reverse=True)
    return scored[:limit]


async def nearest_memories(session: AsyncSession, user_id: uuid.UUID, query: list[float], limit: int = 8) -> list[m.MemoryItem]:
    dialect = session.bind.dialect.name if session.bind is not None else "sqlite"
    if dialect == "postgresql":
        distance = m.MemoryItem.embedding.cosine_distance(query)  # type: ignore[attr-defined]
        stmt = select(m.MemoryItem).where(m.MemoryItem.user_id == user_id).order_by(distance).limit(limit)
        return list((await session.scalars(stmt)).all())
    rows = (await session.scalars(select(m.MemoryItem).where(m.MemoryItem.user_id == user_id))).all()
    scored: list[tuple[m.MemoryItem, float]] = [(r, cosine(query, r.embedding or [])) for r in rows]
    scored.sort(key=lambda t: t[1], reverse=True)
    return [r for r, _ in scored[:limit]]


def as_json(vec: list[float] | None) -> Any:
    return None if vec is None else [round(v, 6) for v in vec]
