"""健康检查接口（阶段4增强：适配器状态自检）。"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app import __version__
from app.core.config import settings

router = APIRouter()


class AdapterStatus(BaseModel):
    name: str
    available: bool
    mode: str  # "real" 或 "mock"


class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str
    adapters: list[AdapterStatus] = []


def _check_adapters() -> list[AdapterStatus]:
    """检查各适配器是否可用（real 或 mock）。"""
    result: list[AdapterStatus] = []

    # LLM
    result.append(AdapterStatus(
        name="llm",
        available=True,
        mode="real" if settings.llm_api_key else "mock",
    ))
    # ASR
    result.append(AdapterStatus(
        name="asr",
        available=True,
        mode="real" if settings.asr_api_key else "mock",
    ))
    # TTS
    result.append(AdapterStatus(
        name="tts",
        available=True,
        mode="real" if settings.tts_api_key else "mock",
    ))
    # RAG
    try:
        from app.rag.retriever import get_rag

        rag = get_rag()
        result.append(AdapterStatus(
            name="rag",
            available=rag.is_ready(),
            mode="chroma",
        ))
    except Exception:
        result.append(AdapterStatus(name="rag", available=False, mode="unknown"))

    return result


@router.get("/health", response_model=HealthResponse, summary="健康检查")
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        version=__version__,
        environment=settings.environment,
        adapters=_check_adapters(),
    )
