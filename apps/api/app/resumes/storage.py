"""Private object storage for resumes and generated documents.

S3-compatible bucket (AWS S3, Cloudflare R2, Backblaze B2, MinIO) when
STORAGE_BUCKET is set; a local folder otherwise. Objects are never public:
downloads go through the API, which checks ownership first.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

from app.config import get_settings

_SAFE = re.compile(r"[^a-zA-Z0-9._/-]")


def safe_key(*parts: str) -> str:
    return "/".join(_SAFE.sub("_", p).strip("/") for p in parts if p)


class Storage:
    name = "base"

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        raise NotImplementedError

    async def get(self, key: str) -> bytes:
        raise NotImplementedError

    async def delete(self, key: str) -> None:
        raise NotImplementedError


class LocalStorage(Storage):
    name = "local"

    def __init__(self, root: str) -> None:
        self.root = Path(root).resolve()

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root not in path.parents and path != self.root:
            raise ValueError("invalid storage key")
        return path

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, data)

    async def get(self, key: str) -> bytes:
        return await asyncio.to_thread(self._path(key).read_bytes)

    async def delete(self, key: str) -> None:
        path = self._path(key)
        if path.exists():
            await asyncio.to_thread(path.unlink)


class S3Storage(Storage):
    name = "s3"

    def __init__(self, bucket: str, endpoint_url: str, region: str, access_key: str, secret_key: str) -> None:
        import boto3

        self.bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url or None,
            region_name=region or None,
            aws_access_key_id=access_key or None,
            aws_secret_access_key=secret_key or None,
        )

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        await asyncio.to_thread(self._client.put_object, Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)

    async def get(self, key: str) -> bytes:
        obj = await asyncio.to_thread(self._client.get_object, Bucket=self.bucket, Key=key)
        return await asyncio.to_thread(obj["Body"].read)

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self._client.delete_object, Bucket=self.bucket, Key=key)


_storage: Storage | None = None


def get_storage() -> Storage:
    global _storage
    if _storage is None:
        s = get_settings()
        if s.storage_bucket:
            _storage = S3Storage(
                s.storage_bucket, s.storage_endpoint_url, s.storage_region, s.storage_access_key_id, s.storage_secret_access_key
            )
        else:
            _storage = LocalStorage(s.storage_local_dir)
    return _storage


def set_storage(storage: Storage | None) -> None:
    global _storage
    _storage = storage
