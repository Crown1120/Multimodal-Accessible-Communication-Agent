"""流式事件协议。

定义后端通过 SSE/WebSocket 推送给前端的统一事件格式与类型。
事件名采用 `<域>.<动作>` 命名，例如 `transcript.partial`。
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class EventType(str, Enum):
    """流式事件类型，对齐开发文档第 9 节。"""

    # 字幕
    TRANSCRIPT_PARTIAL = "transcript.partial"
    TRANSCRIPT_FINAL = "transcript.final"

    # Agent 状态
    AGENT_STARTED = "agent.started"
    AGENT_THINKING = "agent.thinking"
    AGENT_COMPLETED = "agent.completed"

    # 工具
    TOOL_STARTED = "tool.started"
    TOOL_COMPLETED = "tool.completed"
    TOOL_FAILED = "tool.failed"

    # 消息
    MESSAGE_DELTA = "message.delta"
    MESSAGE_COMPLETED = "message.completed"

    # 数字人
    DIGITAL_HUMAN_SPEAK = "digital_human.speak"
    DIGITAL_HUMAN_AUDIO_READY = "digital_human.audio_ready"

    # Widget
    WIDGET_SHOW = "widget.show"
    WIDGET_UPDATE = "widget.update"
    WIDGET_CLOSE = "widget.close"

    # 错误
    ERROR = "error"


class Event(BaseModel):
    """统一事件载荷。"""

    type: EventType
    session_id: str
    data: dict[str, Any] = Field(default_factory=dict)
    # 单调递增序号，便于前端排序与重连恢复
    seq: int = 0


# 各事件 data 字段的推荐结构（作为契约参考）
TranscriptPartialData = dict[str, Any]  # {"text": str, "speaker": str, "is_final": False}
TranscriptFinalData = dict[str, Any]  # {"text": str, "speaker": str, "language": str}
AgentStartedData = dict[str, Any]  # {"run_id": str, "intent": str | None}
AgentThinkingData = dict[str, Any]  # {"step": str, "detail": str}
AgentCompletedData = dict[str, Any]  # {"run_id": str, "summary": str}
ToolStartedData = dict[str, Any]  # {"tool": str, "args": dict}
ToolCompletedData = dict[str, Any]  # {"tool": str, "result": dict}
ToolFailedData = dict[str, Any]  # {"tool": str, "code": str, "message": str}
MessageDeltaData = dict[str, Any]  # {"text": str, "role": str}
MessageCompletedData = dict[str, Any]  # {"message_id": str, "role": str, "content": str}
DigitalHumanSpeakData = dict[str, Any]  # {"text": str, "audio_url": str | None, "emotion": str | None}
DigitalHumanAudioReadyData = dict[str, Any]  # {"audio_url": str, "text": str}
WidgetShowData = dict[str, Any]  # {"widget_id": str, "widget_type": str, "payload": dict}
WidgetUpdateData = dict[str, Any]  # {"widget_id": str, "payload": dict}
WidgetCloseData = dict[str, Any]  # {"widget_id": str}
ErrorData = dict[str, Any]  # {"code": str, "message": str, "details": dict}


def make_event(
    event_type: EventType,
    session_id: str,
    seq: int,
    **data: Any,
) -> Event:
    """构造事件。"""
    return Event(type=event_type, session_id=session_id, seq=seq, data=data)


def to_sse(event: Event) -> str:
    """将事件序列化为 SSE 数据帧（含 id 用于断线重连）。"""
    payload = event.model_dump_json()
    return f"id: {event.seq}\nevent: {event.type.value}\ndata: {payload}\n\n"
