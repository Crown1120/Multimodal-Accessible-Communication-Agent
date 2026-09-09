"""Widget 数据缓存。

Agent 通过 `widget.show` 事件把 Widget 数据推给前端；本模块按 widget_id
保留最近一次数据，供 `GET /api/widgets/{widget_id}` 回查
（前端刷新或 SSE 重连后可补拉，避免丢一次事件就看不到 Widget）。
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict

from app.core.logging import get_logger

logger = get_logger()

# 最多保留的 Widget 数量
_MAX_ITEMS = 256


class WidgetStore:
    def __init__(self, max_items: int = _MAX_ITEMS) -> None:
        self._items: OrderedDict[str, dict] = OrderedDict()
        self._max_items = max_items
        self._lock = asyncio.Lock()

    async def put(self, widget_id: str, *, widget_type: str, payload: dict) -> None:
        async with self._lock:
            self._items[widget_id] = {"widget_type": widget_type, "payload": payload}
            self._items.move_to_end(widget_id)
            while len(self._items) > self._max_items:
                self._items.popitem(last=False)

    async def get(self, widget_id: str) -> dict | None:
        async with self._lock:
            item = self._items.get(widget_id)
            if item is None:
                return None
            self._items.move_to_end(widget_id)
            return dict(item)

    async def clear(self) -> None:
        async with self._lock:
            self._items.clear()


widget_store = WidgetStore()
