"""向量存储抽象与实现。

- VectorStore：统一接口（add / query）
- InMemoryVectorStore：字符 n-gram 余弦，无外部依赖，保证可用
- ChromaVectorStore：基于 Chroma（懒加载，可用时启用）

业务层通过 VectorStore 接口访问，便于后续迁移到 Milvus/pgvector。
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.core.config import settings
from app.core.logging import get_logger
from app.rag.embedding import dot, embed_text, vector_norm

logger = get_logger()


@dataclass
class Document:
    id: str
    text: str
    metadata: dict[str, str] = field(default_factory=dict)
    score: float = 0.0


class VectorStore(Protocol):
    async def clear(self) -> None: ...

    async def add(self, docs: list[Document]) -> None: ...

    async def query(
        self,
        text: str,
        *,
        k: int = 4,
        where: dict[str, str | list[str]] | None = None,
    ) -> list[Document]: ...


class InMemoryVectorStore:
    """进程内向量存储（字符 n-gram 余弦）。"""

    def __init__(self) -> None:
        self._docs: list[Document] = []
        self._vecs: list[Counter[str]] = []
        # 预计算模长，避免每次查询都对全部文档重算（O(N·L) → O(N) 点积）
        self._norms: list[float] = []

    async def clear(self) -> None:
        self._docs = []
        self._vecs = []
        self._norms = []

    async def add(self, docs: list[Document]) -> None:
        for d in docs:
            vec = embed_text(d.text)
            self._docs.append(d)
            self._vecs.append(vec)
            self._norms.append(vector_norm(vec))

    async def query(
        self,
        text: str,
        *,
        k: int = 4,
        where: dict[str, str | list[str]] | None = None,
    ) -> list[Document]:
        q = embed_text(text)
        qn = vector_norm(q)
        if qn == 0:
            return []
        scored: list[Document] = []
        for doc, vec, norm in zip(self._docs, self._vecs, self._norms, strict=True):
            if where and not _match(doc.metadata, where):
                continue
            score = dot(q, vec) / (qn * norm) if norm else 0.0
            scored.append(Document(id=doc.id, text=doc.text, metadata=doc.metadata, score=score))
        scored.sort(key=lambda d: d.score, reverse=True)
        return scored[:k]


def _match(meta: dict[str, str], where: dict[str, str | list[str]]) -> bool:
    """元数据过滤：值为列表时表示「命中其一即可」。"""
    for key, expected in where.items():
        actual = meta.get(key)
        if isinstance(expected, list):
            if actual not in expected:
                return False
        elif actual != expected:
            return False
    return True


def _to_chroma_where(where: dict[str, str | list[str]] | None) -> dict | None:
    """将简单 key=value 字典转为 Chroma 兼容的 where 过滤器。

    Chroma 要求多键条件使用 $and 操作符，多值条件使用 $in：
    {"$and": [{"key": "val1"}, {"key2": {"$in": ["a", "b"]}}]}
    """
    if not where:
        return None
    clauses: list[dict] = []
    for key, value in where.items():
        clauses.append({key: {"$in": list(value)} if isinstance(value, list) else value})
    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses}


class ChromaVectorStore:
    """基于 Chroma 的向量存储（懒加载）。"""

    def __init__(self) -> None:
        # chromadb 是可选依赖，用 Any 避免把它的类型引入到核心模块
        self._client: Any = None
        self._collection: Any = None

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

    def _collection_or_raise(self) -> Any:
        """返回已就绪的 collection。

        原先用 `assert self._collection is not None` 做控制流：`python -O` 会
        把 assert 整个去掉，之后会以 `AttributeError: NoneType` 的形式暴露，
        既难排查也不安全。这里改成显式异常。
        """
        self._ensure()
        if self._collection is None:
            raise RuntimeError("Chroma 集合未就绪")
        return self._collection

    async def clear(self) -> None:
        self._collection_or_raise().delete(where={"content_type": "text"})

    async def add(self, docs: list[Document]) -> None:
        collection = self._collection_or_raise()
        if not docs:
            return
        collection.upsert(
            ids=[d.id for d in docs],
            documents=[d.text for d in docs],
            metadatas=[d.metadata for d in docs],
        )

    async def query(
        self,
        text: str,
        *,
        k: int = 4,
        where: dict[str, str | list[str]] | None = None,
    ) -> list[Document]:
        collection = self._collection_or_raise()
        # Chroma 要求多键 where 使用 $and、多值使用 $in 操作符
        chroma_where = _to_chroma_where(where)
        res = collection.query(query_texts=[text], n_results=k, where=chroma_where)
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
    """默认使用进程内中文 n-gram 向量存储（确定、可靠、无外部模型依赖）。

    Chroma 默认 embedding 对本项目中文语料会产生退化向量（所有文档几乎同向量，
    检索结果与查询无关），因此不再默认启用；仅当通过 settings 显式配置了
    可用 embedding 时才考虑 Chroma。
    """
    try:
        chroma_ef = settings.chroma_embedding  # 若配置了有效 embedding 才用 Chroma
        if not chroma_ef:
            raise RuntimeError("未配置 Chroma embedding，使用内存向量存储")
        return ChromaVectorStore()
    except Exception as e:  # noqa: BLE001
        logger.warning("使用内存向量存储（中文 n-gram）：{}", e)
        return InMemoryVectorStore()
