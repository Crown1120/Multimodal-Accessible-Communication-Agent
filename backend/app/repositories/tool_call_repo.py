"""工具调用记录仓库。

开发文档第 8 节要求持久化 `tool_calls`，但此前该表从未被写入，
工具调用无法审计。此处提供独立会话的写入入口（Agent 图不持有请求级 DB 会话）。
"""

from __future__ import annotations

import secrets

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.database import async_session_factory
from app.models.db_models import ToolCall

logger = get_logger()


def _new_id() -> str:
    return f"tc_{secrets.token_urlsafe(12)}"


class ToolCallRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def add(
        self,
        *,
        agent_run_id: str,
        tool: str,
        args: dict | None = None,
        result: dict | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        duration_ms: int | None = None,
    ) -> ToolCall:
        record = ToolCall(
            id=_new_id(),
            agent_run_id=agent_run_id,
            tool=tool,
            args=args or {},
            result=result,
            error_code=error_code,
            error_message=error_message,
            duration_ms=duration_ms,
        )
        self.db.add(record)
        await self.db.flush()
        return record


async def record_tool_call(
    *,
    agent_run_id: str,
    tool: str,
    args: dict | None = None,
    result: dict | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
    duration_ms: int | None = None,
) -> None:
    """用独立会话记录一次工具调用；失败只记日志，不影响主流程。"""
    try:
        async with async_session_factory() as db:
            repo = ToolCallRepository(db)
            await repo.add(
                agent_run_id=agent_run_id,
                tool=tool,
                args=args,
                result=result,
                error_code=error_code,
                error_message=error_message,
                duration_ms=duration_ms,
            )
            await db.commit()
    except Exception:  # noqa: BLE001
        logger.exception("记录工具调用失败 run={} tool={}", agent_run_id, tool)
