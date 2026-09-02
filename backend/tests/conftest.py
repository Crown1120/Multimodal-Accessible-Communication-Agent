"""pytest 配置与公共 fixtures。"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# 确保后端包可导入
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

# 测试环境：使用内存数据库
os.environ.setdefault("SQLITE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("CHROMA_PATH", str(backend_dir / "test_chroma"))
os.environ.setdefault("LOG_LEVEL", "WARNING")


@pytest.fixture(scope="session")
def event_loop():
    """全局事件循环。"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


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
