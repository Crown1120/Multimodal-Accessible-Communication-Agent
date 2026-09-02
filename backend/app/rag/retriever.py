"""RAG 检索服务。

按场景、语言过滤，返回答案及引用来源。
首次调用自动索引 knowledge/ 目录。
"""

from __future__ import annotations

from app.core.logging import get_logger
from app.rag.indexer import index_knowledge
from app.rag.store import Document, VectorStore, get_vector_store

logger = get_logger()

# 置信度阈值（余弦/Chroma 距离换算后）
LOW_CONFIDENCE = 0.15


class RAGRetriever:
    def __init__(self, store: VectorStore | None = None) -> None:
        self.store = store or get_vector_store()
        self._indexed = False

    async def _ensure_indexed(self) -> None:
        if self._indexed:
            return
        try:
            count = await index_knowledge(self.store)
            logger.info("RAG 初始索引完成，文档块数={}", count)
        except Exception as e:  # noqa: BLE001
            logger.exception("RAG 初始索引失败：{}", e)
        finally:
            self._indexed = True

    async def retrieve(
        self,
        query: str,
        *,
        scene: str | None = None,
        language: str = "zh",
        k: int = 4,
    ) -> list[Document]:
        await self._ensure_indexed()
        where: dict[str, str] = {"language": language}
        if scene:
            where["scene"] = scene
        docs = await self.store.query(query, k=k, where=where)
        return docs

    def is_ready(self) -> bool:
        """RAG 是否已初始化（同步方法，供健康检查用）。"""
        return self._indexed

    async def retrieve_with_sources(
        self,
        query: str,
        *,
        scene: str | None = None,
        language: str = "zh",
        k: int = 4,
    ) -> dict:
        docs = await self.retrieve(query, scene=scene, language=language, k=k)
        top = docs[0] if docs else None
        confident = bool(top and top.score >= LOW_CONFIDENCE)
        context = "\n\n".join(d.text for d in docs) if docs else ""
        sources = [
            {"title": d.metadata.get("title", ""), "source": d.metadata.get("source", ""), "score": round(d.score, 3)}
            for d in docs
        ]
        return {
            "has_result": bool(docs),
            "confident": confident,
            "context": context,
            "sources": sources,
            "top_text": top.text if top else "",
        }


# 单例
_rag: RAGRetriever | None = None


def get_rag() -> RAGRetriever:
    global _rag
    if _rag is None:
        _rag = RAGRetriever()
    return _rag
