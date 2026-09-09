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


# 数据库选择：优先 PostgreSQL，其次 SQLite
_use_postgres = bool(settings.postgres_url)
_is_memory = (not _use_postgres) and (":memory:" in settings.sqlite_url)

if _use_postgres:
    engine = create_async_engine(
        settings.postgres_url,
        echo=settings.sqlite_echo,
        future=True,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
    )
else:
    engine = create_async_engine(
        settings.sqlite_url,
        echo=settings.sqlite_echo,
        future=True,
        connect_args={"check_same_thread": False} if _is_memory else {},
        poolclass=StaticPool if _is_memory else None,
    )


def _set_sqlite_pragma(dbapi_connection, _record) -> None:
    """每条新连接都启用 WAL 与 busy_timeout，避免并发写时 database is locked。

    busy_timeout 是 SQLite 的每连接设置，只在 init_db 里设置一次不会对
    后续连接生效，并发写会立即报 "database is locked"。
    """
    if _use_postgres or _is_memory:
        return
    try:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()
    except Exception:  # noqa: BLE001
        logger.warning("设置 SQLite 连接参数失败", exc_info=True)


from sqlalchemy import event  # noqa: E402

event.listen(engine.sync_engine, "connect", _set_sqlite_pragma)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def init_db() -> None:
    """初始化数据库。

    默认使用 Alembic 迁移（可追溯、可回滚）；若迁移不可用则回退到 create_all，
    保证首次启动仍能建表。
    """
    if settings.auto_migrate:
        from app.models.migrations import run_migrations

        await run_migrations()
    else:
        from app.models import db_models  # noqa: F401

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    # 启用 WAL 模式，解决并发读写导致的 "database is locked"
    if not _use_postgres and not _is_memory:
        async with engine.begin() as conn:
            await conn.execute(text("PRAGMA journal_mode=WAL"))
            await conn.execute(text("PRAGMA busy_timeout=5000"))
    logger.info("数据表已就绪（auto_migrate={}）", settings.auto_migrate)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI 依赖：获取数据库会话。"""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
