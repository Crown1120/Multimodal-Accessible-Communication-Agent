"""会话内事件总线（内存版）。

Agent 运行时向总线发布事件，SSE 端点订阅并推送给前端。
Phase 1 使用进程内实现；后续可替换为 Redis/pubsub 以支持多实例。
"""

from __future__ import annotations

import asyncio
from collections import defaultdict, deque

from app.core.events import Event
from app.core.logging import get_logger

logger = get_logger()

# 每个会话保留最近 N 条事件，用于断线重连恢复
_REPLAY_BUFFER = 256


class _SessionStream:
    def __init__(self) -> None:
        self._queues: list[asyncio.Queue[Event]] = []
        self._buffer: deque[Event] = deque(maxlen=_REPLAY_BUFFER)
        self._seq = 0
        self._lock = asyncio.Lock()

    async def publish(self, event: Event) -> Event:
        async with self._lock:
            self._seq += 1
            event.seq = self._seq
            self._buffer.append(event)
        for q in list(self._queues):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("事件队列已满，丢弃事件：{}", event.type)
        return event

    def next_seq(self) -> int:
        return self._seq + 1

    async def subscribe(self, last_seq: int = 0) -> asyncio.Queue[Event]:
        q: asyncio.Queue[Event] = asyncio.Queue(maxsize=1024)
        # Replay and registration must be atomic, otherwise an event published
        # between these operations can be missed by a reconnecting client.
        async with self._lock:
            for ev in self._buffer:
                if ev.seq > last_seq:
                    try:
                        q.put_nowait(ev)
                    except asyncio.QueueFull:
                        break
            self._queues.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[Event]) -> None:
        if q in self._queues:
            self._queues.remove(q)


class EventBus:
    def __init__(self) -> None:
        self._streams: dict[str, _SessionStream] = defaultdict(_SessionStream)

    def stream(self, session_id: str) -> _SessionStream:
        return self._streams[session_id]

    async def publish(self, session_id: str, event: Event) -> Event:
        return await self.stream(session_id).publish(event)

    async def subscribe(self, session_id: str, last_seq: int = 0) -> asyncio.Queue[Event]:
        return await self.stream(session_id).subscribe(last_seq)

    def unsubscribe(self, session_id: str, q: asyncio.Queue[Event]) -> None:
        self.stream(session_id).unsubscribe(q)

    def drop(self, session_id: str) -> None:
        self._streams.pop(session_id, None)


# 进程内单例
event_bus = EventBus()
