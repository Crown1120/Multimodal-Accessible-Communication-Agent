"""Agent 状态定义（LangGraph）。"""

from __future__ import annotations

from typing import Any

from typing_extensions import TypedDict


class AgentState(TypedDict, total=False):
    """Agent 运行状态。"""

    session_id: str
    run_id: str
    scene: str
    user_text: str
    history: list[dict[str, str]]
    intent: str  # knowledge | route | service | translate | chitchat
    rag_context: str
    rag_sources: list[dict[str, Any]]
    tool_result: dict[str, Any] | None
    widget: dict[str, Any] | None
    reply: str
    error: str | None
