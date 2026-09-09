"""以编程方式执行 Alembic 迁移。

应用启动时可选择自动迁移（`AUTO_MIGRATE=true`）。
对于「已有表结构但没有 alembic_version」的历史数据库，先打上初始版本标记，
避免 `upgrade head` 因表已存在而失败。
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from app.core.config import settings
from app.core.logging import logger
from app.models.database import Base, engine

_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
_INITIAL_REVISION = "17324cf663f8"


def alembic_config() -> Config:
    cfg = Config(str(_BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(_BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", settings.postgres_url or settings.sqlite_url)
    return cfg


async def run_migrations() -> None:
    """把数据库迁移到最新版本。"""
    from app.models import db_models  # noqa: F401  确保 metadata 完整

    cfg = alembic_config()

    async with engine.begin() as conn:

        def _inspect(sync_conn) -> tuple[str | None, bool]:
            """返回 (当前 alembic 版本号, 是否已有业务表)。

            注意：不能用「alembic_version 表是否存在」来判断版本——
            Alembic 在 upgrade 开始时就会建这张表，迁移失败时会留下一个
            空表。历史库（由 create_all 建表、从未用过 Alembic）第一次运行
            就会正好落在这个状态，若按「表存在」处理会去 upgrade 并因
            「table already exists」失败。
            """
            inspector = inspect(sync_conn)
            tables = set(inspector.get_table_names())
            has_app_tables = bool(tables - {"alembic_version"})
            current: str | None = None
            if "alembic_version" in tables:
                row = sync_conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).first()
                current = row[0] if row else None
            return current, has_app_tables

        current_revision, has_app_tables = await conn.run_sync(_inspect)

        if has_app_tables and not current_revision:
            # 历史库：结构与初始迁移一致，直接打标记，后续增量迁移可正常执行
            logger.warning("检测到无版本记录的历史数据库，标记为初始版本 {}", _INITIAL_REVISION)

            def _stamp(sync_conn) -> None:
                cfg.attributes["connection"] = sync_conn
                command.stamp(cfg, _INITIAL_REVISION)

            await conn.run_sync(_stamp)
            return

        def _upgrade(sync_conn) -> None:
            cfg.attributes["connection"] = sync_conn
            command.upgrade(cfg, "head")

        await conn.run_sync(_upgrade)
    logger.info("数据库迁移完成（head）")


async def create_all_fallback() -> None:
    """未启用自动迁移时的兜底：直接建表（仅适用于全新数据库）。"""
    from app.models import db_models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
