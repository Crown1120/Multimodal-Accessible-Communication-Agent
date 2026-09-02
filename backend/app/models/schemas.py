"""Pydantic 请求/响应 Schema。"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.db_models import (
    Message as _Message,
    Session as _Session,
)


class SessionCreate(BaseModel):
    scene: str = Field(default="hospital")
    mode: str = Field(default="standard")
    user_id: str | None = None


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
    role: str = Field(default="user")
    content: str = Field(min_length=1)
    speaker: str | None = None
    language: str = Field(default="zh")
    message_type: str = Field(default="text")


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
    ok: bool = True


class PreferenceSave(BaseModel):
    """用户偏好保存请求。"""

    mode: str | None = None
    font_size: str | None = None
    speech_rate: str | None = None
    language: str | None = None
    high_contrast: bool | None = None
    frequent_places: dict | None = None


class PreferenceOut(BaseModel):
    """用户偏好响应。"""

    id: str
    session_id: str
    font_size: str
    speech_rate: str
    language: str
    high_contrast: bool
    frequent_places: dict = {}
