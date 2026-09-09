"""Pydantic 请求/响应 Schema。

所有外部输入都用 Literal 约束枚举值：这些字段会直接决定前端 `data-*` 属性、
Agent 场景提示词与消息角色，放任任意字符串会带来数据完整性问题
（例如客户端伪造 `role="assistant"` 往对话历史里注入内容）。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.models.db_models import (
    Message as _Message,
    Session as _Session,
)

Scene = Literal["hospital", "government"]
Mode = Literal["standard", "hearing", "elderly"]
ClientRole = Literal["user", "staff"]
FontSize = Literal["small", "medium", "large"]
SpeechRate = Literal["normal", "slow"]

# 消息硬上限：超过该长度直接 422，避免超大请求体
_MESSAGE_HARD_LIMIT = 10000
# frequent_places 最多保存的地点数量
_MAX_FREQUENT_PLACES = 32


class SessionCreate(BaseModel):
    scene: Scene = "hospital"
    mode: Mode = "standard"
    user_id: str | None = Field(default=None, max_length=64)


class SessionOut(BaseModel):
    session_id: str
    scene: str
    mode: str
    status: str

    @classmethod
    def from_orm(cls, obj: _Session) -> SessionOut:
        return cls(
            session_id=obj.id,
            scene=obj.scene,
            mode=obj.mode,
            status=obj.status,
        )


class MessageCreate(BaseModel):
    """发送消息请求。

    注意：`role` 只允许 user/staff。assistant 角色由后端生成，
    若允许客户端传入，就能伪造「助手说过的话」并进入后续 LLM 上下文。
    """

    role: ClientRole = "user"
    content: str = Field(min_length=1, max_length=_MESSAGE_HARD_LIMIT)
    speaker: str | None = Field(default=None, max_length=64)
    language: str = Field(default="zh", max_length=16)
    message_type: Literal["text", "audio", "transcript"] = "text"

    @field_validator("content")
    @classmethod
    def _strip_content(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("消息内容不能为空")
        return stripped


class MessageOut(BaseModel):
    id: str
    session_id: str
    role: str
    content: str
    speaker: str | None = None
    language: str = "zh"
    message_type: str = "text"

    @classmethod
    def from_orm(cls, obj: _Message) -> MessageOut:
        return cls(
            id=obj.id,
            session_id=obj.session_id,
            role=obj.role,
            content=obj.content,
            speaker=obj.speaker,
            language=obj.language,
            message_type=obj.message_type,
        )


class SendMessageResponse(BaseModel):
    run_id: str
    message_id: str


class AudioTranscribeResponse(BaseModel):
    """音频上传后的 ASR 转写结果。"""

    session_id: str
    text: str
    message_id: str | None = None
    run_id: str | None = None  # 本次 Agent 运行的 run_id，前端用于关联流式事件
    ok: bool = True
    asr_adapter: str | None = None  # 当前实际使用的 ASR 适配器，便于前端提示精度


class PreferenceSave(BaseModel):
    """用户偏好保存请求。"""

    mode: Mode | None = None
    font_size: FontSize | None = None
    speech_rate: SpeechRate | None = None
    language: str | None = Field(default=None, max_length=16)
    high_contrast: bool | None = None
    frequent_places: dict | None = None

    @field_validator("frequent_places")
    @classmethod
    def _limit_frequent_places(cls, value: dict | None) -> dict | None:
        if value is not None and len(value) > _MAX_FREQUENT_PLACES:
            raise ValueError(f"常用地点最多 {_MAX_FREQUENT_PLACES} 条")
        return value


class PreferenceOut(BaseModel):
    """用户偏好响应。

    `mode` 存在会话表上，这里一并返回：前端会读取 `pref.mode` 来恢复上次的模式。
    """

    id: str
    session_id: str
    mode: str | None = None
    font_size: str
    speech_rate: str
    language: str
    high_contrast: bool
    frequent_places: dict = {}
