"""Application-scoped management for fire-and-forget asyncio tasks."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any

from app.core.logging import get_logger

logger = get_logger()


class BackgroundTaskManager:
    """Keep background tasks observable and drain them during shutdown."""

    def __init__(self) -> None:
        self._tasks: set[asyncio.Task[Any]] = set()

    def create(self, coroutine: Coroutine[Any, Any, Any], *, name: str) -> asyncio.Task[Any]:
        task = asyncio.create_task(coroutine, name=name)
        self._tasks.add(task)
        task.add_done_callback(self._on_done)
        return task

    def _on_done(self, task: asyncio.Task[Any]) -> None:
        self._tasks.discard(task)
        if task.cancelled():
            return
        try:
            error = task.exception()
        except Exception:  # noqa: BLE001
            logger.exception("后台任务状态读取失败 name={}", task.get_name())
            return
        if error is not None:
            logger.error("后台任务失败 name={} error={}", task.get_name(), error)

    async def shutdown(self) -> None:
        tasks = tuple(self._tasks)
        if not tasks:
            return
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()


background_tasks = BackgroundTaskManager()
