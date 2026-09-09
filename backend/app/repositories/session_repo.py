"""会话与消息仓库。"""

from __future__ import annotations

import itertools
import secrets
import time
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ErrorCode, SessionError
from app.models.db_models import AgentRun, Message, Session

# 进程内单调计数，用于同一毫秒内生成多个 ID 时保持顺序
_id_counter = itertools.count()


def _new_id(prefix: str) -> str:
    """生成「时间有序」的 ID。

    格式：`{prefix}_{毫秒时间戳:013d}{计数器:05d}_{随机后缀}`。

    为什么不用纯随机 ID：`list_messages` 用 `created_at DESC, id DESC` 排序，
    若 id 是随机的，同一时刻（同一事务）写入的多条消息顺序就不确定，
    配合 `limit` 还可能截断错误的行。时间前缀保证字典序与创建顺序一致。
    """
    ts_ms = int(time.time() * 1000)
    seq = next(_id_counter) % 100_000
    return f"{prefix}_{ts_ms:013d}{seq:05d}_{secrets.token_urlsafe(6)}"


def new_run_id() -> str:
    """预先生成 run_id。

    路由在启动后台 Agent 前生成，这样 POST /messages 的响应就能返回
    真正贯穿 agent.started / message.delta / message.completed 的 run_id，
    而不是复用 message_id（旧实现把两者混为一谈，前端无法据此关联事件）。
    """
    return _new_id("run")


class SessionRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, *, scene: str, mode: str, user_id: str | None) -> Session:
        session = Session(
            id=_new_id("sess"),
            user_id=user_id,
            scene=scene,
            mode=mode,
            status="active",
        )
        self.db.add(session)
        await self.db.flush()
        return session

    async def get(self, session_id: str) -> Session:
        stmt = select(Session).where(Session.id == session_id)
        result = await self.db.execute(stmt)
        session = result.scalar_one_or_none()
        if session is None:
            raise SessionError(ErrorCode.SESSION_NOT_FOUND, f"会话不存在：{session_id}")
        if session.status == "closed":
            raise SessionError(ErrorCode.SESSION_CLOSED, "会话已关闭")
        return session

    async def close(self, session_id: str) -> Session:
        session = await self.get(session_id)
        session.status = "closed"
        session.closed_at = datetime.now(timezone.utc)
        await self.db.flush()
        return session

    async def list_messages(
        self, session_id: str, *, limit: int | None = None
    ) -> list[Message]:
        """按时间顺序返回消息。

        id 作为次级排序键保证同一事务内多条消息（时间戳相同）顺序稳定；
        limit 取最近的 N 条（仍按时间升序返回），供 Agent 历史窗口使用，
        避免长会话每轮全表拉取。
        """
        stmt = (
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.created_at.desc(), Message.id.desc())
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self.db.execute(stmt)
        return list(reversed(result.scalars().all()))


class MessageRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def add(
        self,
        *,
        session_id: str,
        role: str,
        content: str,
        speaker: str | None = None,
        language: str = "zh",
        message_type: str = "text",
    ) -> Message:
        message = Message(
            id=_new_id("msg"),
            session_id=session_id,
            role=role,
            content=content,
            speaker=speaker,
            language=language,
            message_type=message_type,
        )
        self.db.add(message)
        await self.db.flush()
        return message


class AgentRunRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(
        self, *, session_id: str, intent: str | None = None, run_id: str | None = None
    ) -> AgentRun:
        run = AgentRun(
            id=run_id or _new_id("run"),
            session_id=session_id,
            intent=intent,
            status="running",
        )
        self.db.add(run)
        await self.db.flush()
        return run

    async def complete(
        self,
        run_id: str,
        *,
        status: str = "completed",
        duration_ms: int | None = None,
        intent: str | None = None,
    ) -> None:
        stmt = select(AgentRun).where(AgentRun.id == run_id)
        run = (await self.db.execute(stmt)).scalar_one_or_none()
        if run is not None:
            run.status = status
            run.duration_ms = duration_ms
            if intent is not None:
                run.intent = intent
            await self.db.flush()
