"""
engine.py — Async SQLAlchemy engine, session factory, and migration runner.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

import asyncpg
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.logger import get_logger

log = get_logger(__name__)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            settings.database_url,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            pool_recycle=3600,
            echo=not settings.is_production,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
            autocommit=False,
        )
    return _session_factory


async def get_session() -> AsyncSession:
    """Dependency: yields an AsyncSession, commits on success, rolls back on error."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def run_migrations() -> None:
    """Run SQL migration files in order (simple file-based strategy)."""
    migrations_dir = Path(__file__).parent.parent.parent / "migrations"
    if not migrations_dir.exists():
        log.warning("migrations_dir_not_found", path=str(migrations_dir))
        return

    raw_url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    conn = await asyncpg.connect(raw_url)
    try:
        # Ensure migrations table exists
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)

        applied = {row["version"] for row in await conn.fetch("SELECT version FROM schema_migrations")}
        files = sorted(migrations_dir.glob("*.sql"), key=lambda p: int(p.stem.split("_")[0]))

        for f in files:
            version = int(f.stem.split("_")[0])
            if version in applied:
                continue
            log.info("applying_migration", file=f.name)
            sql = f.read_text(encoding="utf-8")
            await conn.execute(sql)
            log.info("migration_applied", version=version)
    finally:
        await conn.close()


async def check_db_health() -> dict:
    """Return DB health info for /health endpoint."""
    import time
    start = time.perf_counter()
    try:
        raw_url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
        conn = await asyncio.wait_for(asyncpg.connect(raw_url), timeout=5.0)
        await conn.fetchval("SELECT 1")
        await conn.close()
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        return {"status": "ok", "latency_ms": latency_ms}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}
