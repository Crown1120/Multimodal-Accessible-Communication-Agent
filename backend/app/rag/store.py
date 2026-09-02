"""向量存储抽象与实现。

- VectorStore：统一接口（add / query）
- InMemoryVectorStore：字符 n-gram 余弦，无外部依赖，保证可用
- ChromaVectorStore：基于 Chroma（懒加载，可用时启用）

业务层通过 VectorStore 接口访问，便于后续迁移到 Milvus/pgvector。
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Protocol

from app.core.config import settings
from app.core.logging import get_logger
from app.rag.embedding import cosine, embed_text

logger = get_logger()


@dataclass
class Document:
    id: str
    text: str
    metadata: dict[str, str] = field(default_factory=dict)
    score: float = 0.0


class VectorStore(Protocol):
    async def add(self, docs: list[Document]) -> None: ...

    async def query(
        self,
        text: str,
        *,
        k: int = 4,
        where: dict[str, str] | None = None,
    ) -> list[Document]: ...


class InMemoryVectorStore:
    """进程内向量存储（字符 n-gram 余弦）。"""

    def __init__(self) -> None:
        self._docs: list[Document] = []
        self._vecs: list[Counter[str]] = []

    async def add(self, docs: list[Document]) -> None:
        for d in docs:
            self._docs.append(d)
            self._vecs.append(embed_text(d.text))

    async def query(
        self,
        text: str,
        *,
        k: int = 4,
        where: dict[str, str] | None = None,
    ) -> list[Document]:
        q = embed_text(text)
        scored: list[Document] = []
        for doc, vec in zip(self._docs, self._vecs, strict=True):
            if where and not _match(doc.metadata, where):
                continue
            score = cosine(q, vec)
            scored.append(Document(id=doc.id, text=doc.text, metadata=doc.metadata, score=score))
        scored.sort(key=lambda d: d.score, reverse=True)
        return scored[:k]


def _match(meta: dict[str, str], where: dict[str, str]) -> bool:
    return all(meta.get(key) == val for key, val in where.items())


def _to_chroma_where(where: dict[str, str] | None) -> dict | None:
    """将简单 key=value 字典转为 Chroma 兼容的 where 过滤器。

    Chroma 要求多键条件使用 $and 操作符：
    {"$and": [{"key": "val1"}, {"key2": "val2"}]}
    """
    if not where:
        return None
    if len(where) == 1:
        return dict(where)
    return {"$and": [{k: v} for k, v in where.items()]}


class ChromaVectorStore:
    """基于 Chroma 的向量存储（懒加载）。"""

    def __init__(self) -> None:
        self._client = None
        self._collection = None

    def _ensure(self) -> None:
        if self._client is not None:
            return
        import chromadb  # 懒加载

        self._client = chromadb.PersistentClient(path=settings.chroma_path)
        self._collection = self._client.get_or_create_collection(
            name=settings.chroma_collection,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info("Chroma 集合已就绪：{}", settings.chroma_collection)

    async def add(self, docs: list[Document]) -> None:
        self._ensure()
        assert self._collection is not None
        if not docs:
            return
        self._collection.upsert(
            ids=[d.id for d in docs],
            documents=[d.text for d in docs],
            metadatas=[d.metadata for d in docs],
        )

    async def query(
        self,
        text: str,
        *,
        k: int = 4,
        where: dict[str, str] | None = None,
    ) -> list[Document]:
        self._ensure()
        assert self._collection is not None
        # Chroma 要求多键 where 使用 $and 操作符
        chroma_where = _to_chroma_where(where)
        res = self._collection.query(query_texts=[text], n_results=k, where=chroma_where)
        out: list[Document] = []
        ids = (res.get("ids") or [[]])[0]
        documents = (res.get("documents") or [[]])[0]
        metadatas = (res.get("metadatas") or [[]])[0]
        distances = (res.get("distances") or [[]])[0]
        for i in range(len(ids)):
            score = 1.0 - (distances[i] if i < len(distances) else 0.0)
            out.append(
                Document(
                    id=ids[i],
                    text=documents[i] if i < len(documents) else "",
                    metadata=(metadatas[i] if i < len(metadatas) else {}) or {},
                    score=score,
                )
            )
        return out


def get_vector_store() -> VectorStore:
    """优先使用 Chroma；不可用时回退到内存向量存储。"""
    try:
        import chromadb  # noqa: F401

        return ChromaVectorStore()
    except Exception as e:  # noqa: BLE001
        logger.warning("Chroma 不可用，回退到内存向量存储：{}", e)
        return InMemoryVectorStore()
