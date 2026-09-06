"""知识库热加载监控器。

轻量轮询实现（无外部依赖）：每隔 interval 秒检查 knowledge/ 目录下
.md 文件的修改时间，发现变化时自动重建向量索引。

使用：
    watcher = KnowledgeWatcher(rag)
    await watcher.start()
    # ... 应用运行 ...
    await watcher.stop()
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from app.core.logging import get_logger
from app.rag.retriever import RAGRetriever

logger = get_logger()

_KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent.parent.parent / "knowledge"


class KnowledgeWatcher:
    """知识库文件变化监控器。"""

    def __init__(self, rag: RAGRetriever, interval: float = 5.0) -> None:
        self._rag = rag
        self._interval = interval
        self._task: asyncio.Task | None = None
        self._mtimes: dict[str, float] = {}

    async def start(self) -> None:
        """启动监控（首次先建索引，然后轮询）。"""
        if self._task is not None:
            return
        # 首次索引
        await self._rebuild(initial=True)
        self._task = asyncio.create_task(self._watch_loop(), name="knowledge-watcher")
        logger.info("知识库热加载监控已启动，间隔={}s，目录={}", self._interval, _KNOWLEDGE_DIR)

    async def stop(self) -> None:
        """停止监控。"""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
            logger.info("知识库热加载监控已停止")

    async def _watch_loop(self) -> None:
        while True:
            await asyncio.sleep(self._interval)
            try:
                if self._has_changed():
                    logger.info("检测到知识库文件变化，正在重建索引...")
                    await self._rebuild(initial=False)
            except Exception:  # noqa: BLE001
                logger.exception("知识库热加载检查失败")

    def _has_changed(self) -> bool:
        """检查 knowledge/ 下 .md 文件是否有变化。"""
        if not _KNOWLEDGE_DIR.exists():
            return False
        current: dict[str, float] = {}
        for md in _KNOWLEDGE_DIR.glob("*.md"):
            try:
                current[md.name] = md.stat().st_mtime
            except OSError:
                continue
        changed = current != self._mtimes
        if changed:
            self._mtimes = current
        return changed

    async def _rebuild(self, *, initial: bool) -> None:
        """通过 RAG 服务重建索引。"""
        count = await self._rag.reindex()
        if initial:
            logger.info("知识库初始索引完成：{} 个文档块", count)
        else:
            logger.info("知识库热重建完成：{} 个文档块", count)
