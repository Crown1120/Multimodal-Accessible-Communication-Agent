"""知识库路由：重建索引。"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.rag.retriever import get_rag

router = APIRouter()


class ReindexResponse(BaseModel):
    indexed: int
    message: str


@router.post("/reindex", response_model=ReindexResponse, summary="重建知识库索引")
async def reindex() -> ReindexResponse:
    rag = get_rag()
    count = await rag.reindex()
    return ReindexResponse(indexed=count, message=f"已索引 {count} 个文档块")
