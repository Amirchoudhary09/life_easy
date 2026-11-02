from __future__ import annotations

import asyncio
import os
from pathlib import Path

import asyncpg


async def migrate() -> None:
    dsn = os.getenv("DATABASE_URL", "")
    if not dsn:
        raise RuntimeError("DATABASE_URL is required to run migrations")
    migrations_dir = Path(__file__).resolve().parent.parent / "migrations"
    connection = await asyncpg.connect(dsn)
    try:
        await connection.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)
        for migration_path in sorted(migrations_dir.glob("*.sql")):
            applied = await connection.fetchval(
                "SELECT EXISTS(SELECT 1 FROM schema_migrations WHERE version=$1)",
                migration_path.name,
            )
            if applied:
                print(f"Skipping {migration_path.name}: already applied")
                continue
            async with connection.transaction():
                await connection.execute(migration_path.read_text(encoding="utf-8"))
                await connection.execute(
                    "INSERT INTO schema_migrations(version) VALUES($1)",
                    migration_path.name,
                )
            print(f"Applied {migration_path.name}")
    finally:
        await connection.close()


if __name__ == "__main__":
    asyncio.run(migrate())
