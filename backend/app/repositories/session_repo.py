"""会话与消息仓库。"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ErrorCode, SessionError
from app.models.db_models import AgentRun, Message, Session


def _new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_urlsafe(12)}"


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

    async def list_messages(self, session_id: str) -> list[Message]:
        stmt = (
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.created_at)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())


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

    async def create(self, *, session_id: str, intent: str | None = None) -> AgentRun:
        run = AgentRun(
            id=_new_id("run"),
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
    ) -> None:
        stmt = select(AgentRun).where(AgentRun.id == run_id)
        run = (await self.db.execute(stmt)).scalar_one_or_none()
        if run is not None:
            run.status = status
            run.duration_ms = duration_ms
            await self.db.flush()
