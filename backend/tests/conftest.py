"""pytest 配置与公共 fixtures。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# 确保后端包可导入
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

# 测试环境：使用内存数据库
os.environ.setdefault("SQLITE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("CHROMA_PATH", str(backend_dir / "test_chroma"))
os.environ.setdefault("LOG_LEVEL", "WARNING")

# 事件循环策略由 pytest-asyncio 的 asyncio_mode=auto 管理
# （pyproject.toml [tool.pytest.ini_options]）；
# pytest-asyncio 1.x 已移除对自定义 event_loop fixture 的支持，不再定义。


@pytest_asyncio.fixture(autouse=True)
async def _dispose_db_engine():
    """每个测试结束后在当前事件循环内释放引擎连接。

    内存 SQLite 使用 StaticPool（全局单连接），而 pytest-asyncio 每个测试函数
    使用独立事件循环；若不在当前循环关闭连接，旧连接会在新循环里被 GC，
    触发 aiosqlite「coroutine ignored GeneratorExit」/ OperationalError。
    """
    yield
    from app.models.database import engine

    await engine.dispose()


@pytest_asyncio.fixture
async def db_session():
    """独立的数据库会话（内存）。"""
    from app.models.database import async_session_factory, init_db

    await init_db()
    async with async_session_factory() as db:
        yield db


@pytest_asyncio.fixture
async def client():
    """FastAPI 测试客户端。"""
    from app.main import app
    from app.models.database import init_db

    await init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
