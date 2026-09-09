"""Bridge 后端应用入口。

负责 FastAPI 实例创建、中间件、异常处理、路由注册和生命周期。
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings
from app.core.errors import BridgeError, ErrorCode
from app.core.logging import get_logger, setup_logging
from app.core.middleware import RequestContextMiddleware

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

    # 回收上次进程被强杀时遗留的 running 运行
    from app.agent.runner import recover_stuck_runs

    await recover_stuck_runs()

    # 知识库索引 + 热加载监控
    from app.core.task_manager import background_tasks
    from app.rag.retriever import get_rag
    from app.rag.watcher import KnowledgeWatcher

    watcher = KnowledgeWatcher(get_rag())
    await watcher.start()

    yield

    await watcher.stop()
    await background_tasks.shutdown()
    # 释放共享 HTTP 连接池与 TTS 音频缓存
    from app.core.http import close_http_client
    from app.services.audio_store import audio_store

    await close_http_client()
    await audio_store.clear()
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
        expose_headers=["X-Request-ID"],
    )
    # 请求上下文（request_id + 访问日志）
    app.add_middleware(RequestContextMiddleware)

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

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_req: Request, exc: RequestValidationError):
        """把 Pydantic 校验错误统一成 Bridge 错误结构。

        默认 FastAPI 返回 `{"detail": [...]}`，前端拿不到 `code`/`message`，
        只能显示「HTTP 422」，对用户毫无意义。
        """
        return JSONResponse(
            status_code=422,
            content={
                "code": ErrorCode.VALIDATION_ERROR.value,
                "message": "请求参数不合法",
                "details": {
                    "errors": [
                        {"loc": list(e.get("loc", ())), "msg": e.get("msg", "")}
                        for e in exc.errors()[:5]
                    ]
                },
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(_req: Request, exc: StarletteHTTPException):
        """HTTPException（401/404/413/429 等）也走统一错误结构。"""
        code_map = {
            401: ErrorCode.UNAUTHORIZED.value,
            403: ErrorCode.UNAUTHORIZED.value,
            404: ErrorCode.NOT_FOUND.value,
            413: ErrorCode.VALIDATION_ERROR.value,
            429: ErrorCode.BAD_REQUEST.value,
        }
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": code_map.get(exc.status_code, ErrorCode.BAD_REQUEST.value),
                "message": str(exc.detail),
                "details": {},
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
