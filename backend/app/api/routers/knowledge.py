"""知识库路由：重建索引。"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.rag.indexer import index_knowledge
from app.rag.retriever import get_rag

router = APIRouter()


class ReindexResponse(BaseModel):
    indexed: int
    message: str


@router.post("/reindex", response_model=ReindexResponse, summary="重建知识库索引")
async def reindex() -> ReindexResponse:
    rag = get_rag()
    # 重置索引标记以强制重建
    rag._indexed = True  # 跳过自动索引，直接重建
    count = await index_knowledge(rag.store)
    return ReindexResponse(indexed=count, message=f"已索引 {count} 个文档块")
