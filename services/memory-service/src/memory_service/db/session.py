"""Database session factory."""

from __future__ import annotations

import os

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from memory_service.db.models import Base

_DB_URL = os.environ.get(
    "DATABASE_URL",
    "sqlite+aiosqlite:///./data/aura-memory.db",
)

engine = create_async_engine(_DB_URL, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
