"""Alembic 迁移环境（异步）。

数据库连接串直接取自应用配置（`app.core.config.settings`），
避免 alembic.ini 与 .env 两处配置不一致。
"""

import asyncio
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# 让 `alembic` 能导入 app 包（在 backend/ 目录下执行时）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings  # noqa: E402
from app.models.database import Base  # noqa: E402

# 导入所有模型，确保 metadata 完整
from app.models import db_models  # noqa: E402,F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 迁移使用的连接串：优先 PostgreSQL，其次 SQLite
config.set_main_option(
    "sqlalchemy.url",
    settings.postgres_url or settings.sqlite_url,
)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """离线模式：仅生成 SQL。"""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # SQLite 不支持多数 ALTER，需用 batch 模式重建表
        render_as_batch=connection.dialect.name == "sqlite",
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    engine = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await engine.dispose()


def run_migrations_online() -> None:
    """在线模式。

    若调用方（app.models.migrations）已传入同步连接，直接复用——
    此时事件循环正在运行，不能再调用 asyncio.run()。
    """
    existing = config.attributes.get("connection")
    if existing is not None:
        do_run_migrations(existing)
        return
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
