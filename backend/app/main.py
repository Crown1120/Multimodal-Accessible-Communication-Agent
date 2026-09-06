"""Bridge 后端应用入口。

负责 FastAPI 实例创建、中间件、异常处理、路由注册和生命周期。
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.errors import BridgeError, ErrorCode
from app.core.logging import get_logger, setup_logging

logger = get_logger()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """应用生命周期：启动与关闭。"""
    setup_logging()
    logger.info("Bridge 后端启动中，环境={}，版本={}", settings.environment, settings.app_version)

    # 数据库初始化（延迟导入避免循环依赖）
    from app.models.database import init_db

    await init_db()
    logger.info("数据库初始化完成")

    # 知识库索引 + 热加载监控
    from app.rag.retriever import get_rag
    from app.rag.watcher import KnowledgeWatcher
    from app.core.task_manager import background_tasks

    watcher = KnowledgeWatcher(get_rag())
    await watcher.start()

    yield

    await watcher.stop()
    await background_tasks.shutdown()
    logger.info("Bridge 后端关闭")


def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用。"""
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Bridge 多模态无障碍沟通智能体后端",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 统一异常处理
    @app.exception_handler(BridgeError)
    async def handle_bridge_error(_req: Request, exc: BridgeError):
        return JSONResponse(
            status_code=400,
            content={
                "code": exc.code.value,
                "message": exc.message,
                "details": exc.details,
            },
        )

    # 全局兜底异常处理（保证前端始终收到 JSON 错误）
    @app.exception_handler(Exception)
    async def handle_unexpected(_req: Request, exc: Exception):
        logger.exception("未处理异常")
        return JSONResponse(
            status_code=500,
            content={
                "code": ErrorCode.INTERNAL_ERROR.value,
                "message": "服务内部错误，请稍后重试",
                "details": {"reason": str(exc)[:200]},
            },
        )

    # 路由注册
    from app.api.routes import api_router

    app.include_router(api_router, prefix=settings.api_prefix)

    return app


app = create_app()
