"""数据库引擎与会话管理。

使用 SQLAlchemy 2.0 异步 + aiosqlite。业务层通过 Repository 接口访问，
便于后续迁移到 PostgreSQL。
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import StaticPool
from sqlalchemy import text

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger()


class Base(DeclarativeBase):
    """所有 ORM 模型的基类。"""


_is_memory = ":memory:" in settings.sqlite_url

engine = create_async_engine(
    settings.sqlite_url,
    echo=settings.sqlite_echo,
    future=True,
    connect_args={"check_same_thread": False} if _is_memory else {},
    poolclass=StaticPool if _is_memory else None,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def init_db() -> None:
    """创建数据表。"""
    # 导入所有模型，确保元数据注册
    from app.models import db_models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # 启用 WAL 模式，解决并发读写导致的 "database is locked"
        if not _is_memory:
            await conn.execute(text("PRAGMA journal_mode=WAL"))
            await conn.execute(text("PRAGMA busy_timeout=5000"))
    logger.info("数据表已就绪")


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI 依赖：获取数据库会话。"""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
