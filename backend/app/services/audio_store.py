"""TTS 音频临时存储（进程内 LRU）。

为什么需要它：
把 base64 音频塞进 SSE 事件会带来三个问题——
1. 单条 SSE 帧膨胀到几十~上百 KB；
2. 事件总线为断线重放保留 256 条事件，音频因此长期驻留内存；
3. 浏览器无法缓存、无法流式播放。

改为：音频存本模块，SSE 事件只携带 `/api/audio/{id}` 短路径，
由 `GET /api/audio/{audio_id}` 以 `audio/mpeg` 返回字节流。
"""

from __future__ import annotations

import asyncio
import secrets
from collections import OrderedDict

from app.core.logging import get_logger

logger = get_logger()

# 最多保留的音频条数（每条约 10~60KB）；超出按 LRU 淘汰
_MAX_ITEMS = 64


class AudioStore:
    """进程内音频缓存。

    多实例部署时应替换为对象存储 / Redis，接口保持不变。
    """

    def __init__(self, max_items: int = _MAX_ITEMS) -> None:
        self._items: OrderedDict[str, tuple[bytes, str]] = OrderedDict()
        self._max_items = max_items
        self._lock = asyncio.Lock()

    async def put(self, data: bytes, *, mime: str = "audio/mpeg") -> str:
        """存入音频，返回可公开访问的 audio_id。"""
        audio_id = secrets.token_urlsafe(12)
        async with self._lock:
            self._items[audio_id] = (data, mime)
            self._items.move_to_end(audio_id)
            while len(self._items) > self._max_items:
                self._items.popitem(last=False)
        return audio_id

    async def get(self, audio_id: str) -> tuple[bytes, str] | None:
        """读取音频（命中会刷新 LRU 位置）。"""
        async with self._lock:
            item = self._items.get(audio_id)
            if item is None:
                return None
            self._items.move_to_end(audio_id)
            return item

    async def clear(self) -> None:
        async with self._lock:
            self._items.clear()

    def __len__(self) -> int:
        return len(self._items)


audio_store = AudioStore()
