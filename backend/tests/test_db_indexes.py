"""复合索引存在性：历史消息与运行回收查询走索引。"""

from __future__ import annotations


def _index_columns(model) -> set[tuple[str, ...]]:
    return {tuple(c.name for c in ix.columns) for ix in model.__table__.indexes}


def test_messages_session_created_composite_index() -> None:
    from app.models.db_models import Message

    assert ("session_id", "created_at") in _index_columns(Message)


def test_agent_runs_status_created_composite_index() -> None:
    from app.models.db_models import AgentRun

    assert ("status", "created_at") in _index_columns(AgentRun)
