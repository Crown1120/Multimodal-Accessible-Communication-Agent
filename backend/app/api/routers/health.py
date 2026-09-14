"""健康检查接口（阶段4增强：适配器状态自检）。"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app import __version__
from app.core.config import settings

router = APIRouter()


class AdapterStatus(BaseModel):
    name: str
    available: bool
    mode: str  # "real" 或 "mock"
    configured: bool = False
    state: str = "unknown"  # mock/configured/ready/degraded/failed


class DatabaseStatus(BaseModel):
    type: str
    connected: bool
    detail: str = ""


class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str
    uptime_seconds: float
    adapters: list[AdapterStatus] = Field(default_factory=list)
    database: DatabaseStatus | None = None


_START_TIME = __import__("time").time()


async def _check_database() -> DatabaseStatus:
    """检查数据库连通性（执行简单查询）。"""
    try:
        from sqlalchemy import text

        from app.models.database import _use_postgres, engine
        db_type = "postgresql" if _use_postgres else "sqlite"
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return DatabaseStatus(type=db_type, connected=True, detail="ok")
    except Exception as e:
        return DatabaseStatus(type="unknown", connected=False, detail=str(e)[:200])


def _check_adapters() -> list[AdapterStatus]:
    """检查各适配器是否可用（real 或 mock）。"""
    result: list[AdapterStatus] = []

    # LLM
    result.append(AdapterStatus(
        name="llm",
        available=True,
        mode="real" if settings.llm_api_key else "mock",
        configured=bool(settings.llm_api_key),
        state="configured" if settings.llm_api_key else "mock",
    ))
    # ASR：配置云端 Key 但处于冷却降级期时，如实标注为降级，而不是谎报 real
    from app.adapters.asr import _volc_in_cooldown  # noqa: PLC0415

    asr_configured = bool(settings.volc_asr_app_key or settings.asr_api_key)
    asr_degraded = bool(settings.volc_asr_app_key and _volc_in_cooldown())
    result.append(AdapterStatus(
        name="asr",
        available=True,
        mode="degraded" if asr_degraded else ("real" if asr_configured else "mock"),
        configured=asr_configured,
        state="degraded" if asr_degraded else ("configured" if asr_configured else "mock"),
    ))
    # TTS：TTS 未单独配 Key 时会复用火山 ASR 的共享 Key（与 get_tts_adapter 逻辑一致）
    tts_configured = bool(settings.tts_api_key or settings.volc_asr_app_key)
    result.append(AdapterStatus(
        name="tts",
        available=True,
        mode="real" if tts_configured else "mock",
        configured=tts_configured,
        state="configured" if tts_configured else "mock",
    ))
    # RAG
    try:
        from app.core.config import settings as _settings
        from app.rag.retriever import get_rag

        rag = get_rag()
        # 不再硬编码 "chroma"：默认后端是内存中文 n-gram 检索
        rag_mode = "chroma" if _settings.chroma_embedding else "in-memory"
        result.append(AdapterStatus(
            name="rag",
            available=rag.is_ready(),
            mode=rag_mode,
            configured=True,
            state="ready" if rag.is_ready() else "failed",
        ))
    except Exception:
        result.append(AdapterStatus(name="rag", available=False, mode="unknown", configured=True, state="failed"))

    return result


@router.get("/health", response_model=HealthResponse, summary="健康检查")
async def health() -> HealthResponse:
    import time
    database = await _check_database()
    adapters = _check_adapters()
    # `/health` 保持向后兼容，只代表进程和数据库基本可响应；依赖是否完成
    # 初始化由 `/health/ready` 判断，避免冷启动时被存活探针误杀。
    status = "ok" if database.connected else "degraded"
    return HealthResponse(
        status=status,
        version=__version__,
        environment=settings.environment,
        uptime_seconds=round(time.time() - _START_TIME, 1),
        adapters=adapters,
        database=database,
    )


@router.get("/health/live", summary="存活检查")
async def liveness() -> dict[str, str]:
    """只确认进程存活，不访问数据库或外部适配器。"""
    return {"status": "ok"}


@router.get("/health/ready", response_model=None, summary="就绪检查")
async def readiness() -> JSONResponse | HealthResponse:
    """检查数据库和已初始化的 RAG；未就绪时返回 503。"""
    response = await health()
    rag_ready = all(a.available for a in response.adapters if a.name == "rag")
    if response.database is None or not response.database.connected or not rag_ready:
        return JSONResponse(status_code=503, content=response.model_dump(mode="json"))
    return response
