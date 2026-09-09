"""会话内事件总线（内存版）。

Agent 运行时向总线发布事件，SSE 端点订阅并推送给前端。
Phase 1 使用进程内实现；后续可替换为 Redis/pubsub 以支持多实例。

内存管理：
- 每个会话保留最近 N 条事件用于断线重连重放；
- 最后一个订阅者离开后，宽限一段时间（便于重连补齐）再释放该会话的全部状态；
- 会话关闭时立即释放（`drop`）。

背压：
- 订阅队列满时不再静默丢弃事件，而是标记该订阅「已溢出」，
  SSE 端点据此主动断开连接，前端重连时用 last_event_id 补齐缺失事件。
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque

from app.core.events import Event
from app.core.logging import get_logger

logger = get_logger()

# 每个会话保留最近 N 条事件，用于断线重连恢复
_REPLAY_BUFFER = 256
# 单个订阅者的队列容量
_QUEUE_MAXSIZE = 1024
# 最后一个订阅者离开后，保留会话状态多久（秒），便于断线重连补齐
_REPLAY_GRACE_S = 300.0


class Subscriber:
    """单个 SSE 订阅者。"""

    __slots__ = ("queue", "overflowed")

    def __init__(self, maxsize: int = _QUEUE_MAXSIZE) -> None:
        self.queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=maxsize)
        self.overflowed = False


class _SessionStream:
    def __init__(self) -> None:
        self._subscribers: list[Subscriber] = []
        self._buffer: deque[Event] = deque(maxlen=_REPLAY_BUFFER)
        self._seq = 0
        self._lock = asyncio.Lock()
        self._last_active = time.monotonic()
        self._drop_handle: asyncio.TimerHandle | None = None
        self._generation = 0

    async def publish(self, event: Event) -> Event:
        async with self._lock:
            self._seq += 1
            event.seq = self._seq
            self._buffer.append(event)
        self._last_active = time.monotonic()
        for sub in list(self._subscribers):
            if sub.overflowed:
                continue
            try:
                sub.queue.put_nowait(event)
            except asyncio.QueueFull:
                # 不再静默丢弃：标记溢出，由 SSE 端点断开连接让前端重连补齐
                sub.overflowed = True
                logger.warning(
                    "订阅队列已满，将断开该连接以触发重连补齐：session_seq={} type={}",
                    event.seq,
                    event.type.value,
                )
        return event

    def next_seq(self) -> int:
        return self._seq + 1

    async def subscribe(self, last_seq: int = 0) -> Subscriber:
        sub = Subscriber()
        # Replay and registration must be atomic, otherwise an event published
        # between these operations can be missed by a reconnecting client.
        async with self._lock:
            for ev in self._buffer:
                if ev.seq > last_seq:
                    try:
                        sub.queue.put_nowait(ev)
                    except asyncio.QueueFull:
                        break
            self._subscribers.append(sub)
        self._cancel_drop()
        self._last_active = time.monotonic()
        return sub

    def unsubscribe(self, sub: Subscriber) -> None:
        if sub in self._subscribers:
            self._subscribers.remove(sub)
        self._last_active = time.monotonic()
        if not self._subscribers:
            self._schedule_drop()

    # ---- 延迟释放 ----

    def _cancel_drop(self) -> None:
        self._generation += 1
        if self._drop_handle is not None:
            self._drop_handle.cancel()
            self._drop_handle = None

    def _schedule_drop(self) -> None:
        """最后一个订阅者离开后，宽限期结束即释放该会话状态。"""
        self._cancel_drop()
        generation = self._generation
        loop = asyncio.get_running_loop()

        def _on_timeout() -> None:
            # 期间若有新订阅，generation 会变化，则放弃本次释放
            if generation != self._generation:
                return
            _drop_idle_stream(self)

        self._drop_handle = loop.call_later(_REPLAY_GRACE_S, _on_timeout)

    def cancel_timers(self) -> None:
        self._cancel_drop()


class EventBus:
    def __init__(self) -> None:
        self._streams: dict[str, _SessionStream] = defaultdict(_SessionStream)

    def stream(self, session_id: str) -> _SessionStream:
        return self._streams[session_id]

    async def publish(self, session_id: str, event: Event) -> Event:
        return await self.stream(session_id).publish(event)

    async def subscribe(self, session_id: str, last_seq: int = 0) -> Subscriber:
        return await self.stream(session_id).subscribe(last_seq)

    def unsubscribe(self, session_id: str, sub: Subscriber) -> None:
        self.stream(session_id).unsubscribe(sub)

    def drop(self, session_id: str) -> None:
        """立即释放会话的全部事件状态（会话关闭 / 空闲超时）。"""
        stream = self._streams.pop(session_id, None)
        if stream is not None:
            stream.cancel_timers()

    def has_session(self, session_id: str) -> bool:
        return session_id in self._streams

    def session_count(self) -> int:
        return len(self._streams)


def _drop_idle_stream(stream: _SessionStream) -> None:
    """释放空闲 stream：从 _streams 中移除对应项。"""
    for sid, candidate in list(event_bus._streams.items()):  # noqa: SLF001
        if candidate is stream:
            event_bus.drop(sid)
            logger.info("会话事件状态已释放（空闲超时）：session={}", sid)
            return


# 进程内单例
event_bus = EventBus()
