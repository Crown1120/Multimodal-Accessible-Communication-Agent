"""Memory 服务（用户偏好 + 短期记忆）。

对应开发文档第 7.4 节：
- 短期记忆：当前会话消息和任务状态（由 SessionRepository 管理）
- 用户偏好：字体、语速、语言和常用地点（本模块持久化）
- 任务记忆：已确认地点、路线（存入 frequent_places）
- 长期记忆需授权，支持清除
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.repositories.preference_repo import PreferenceRepository

logger = get_logger()

# 模式与偏好映射
_MODE_TO_FONT = {
    "standard": "medium",
    "hearing": "large",
    "elderly": "large",
    "visual": "large",
}
_MODE_TO_SPEECH = {
    "standard": "normal",
    "hearing": "slow",
    "elderly": "slow",
    "visual": "slow",
}
_MODE_TO_CONTRAST = {
    "standard": False,
    "hearing": True,
    "elderly": False,
    "visual": True,
}


class MemoryService:
    """用户偏好持久化与记忆管理。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self._repo = PreferenceRepository(db)

    async def save_preferences(
        self,
        session_id: str,
        *,
        mode: str | None = None,
        font_size: str | None = None,
        speech_rate: str | None = None,
        language: str | None = None,
        high_contrast: bool | None = None,
        wheelchair_mode: bool | None = None,
        frequent_places: dict | None = None,
        user_id: str | None = None,
    ) -> dict:
        """保存用户偏好（局部更新：未传字段保持原值，首次创建时按模式联动默认值）。"""
        existing = await self._repo.get_by_session(session_id)
        merged_places: dict | None
        if existing is not None:
            # 已有偏好：只覆盖本次显式传入的字段，避免「只开关轮椅模式却重置字号/语速」
            merged_font = font_size or existing.font_size
            merged_speech = speech_rate or existing.speech_rate
            merged_language = language or existing.language
            merged_contrast = (
                high_contrast if high_contrast is not None else existing.high_contrast
            )
            merged_wheelchair = (
                wheelchair_mode if wheelchair_mode is not None else existing.wheelchair_mode
            )
            merged_places = (
                frequent_places if frequent_places is not None else existing.frequent_places
            )
        else:
            # 首次创建：模式联动默认值
            if mode:
                font_size = font_size or _MODE_TO_FONT.get(mode, "medium")
                speech_rate = speech_rate or _MODE_TO_SPEECH.get(mode, "normal")
                high_contrast = (
                    high_contrast
                    if high_contrast is not None
                    else _MODE_TO_CONTRAST.get(mode, False)
                )
            merged_font = font_size or "medium"
            merged_speech = speech_rate or "normal"
            merged_language = language or "zh"
            merged_contrast = high_contrast or False
            merged_wheelchair = wheelchair_mode or False
            merged_places = frequent_places

        pref = await self._repo.upsert_by_session(
            session_id,
            font_size=merged_font,
            speech_rate=merged_speech,
            language=merged_language,
            high_contrast=merged_contrast,
            wheelchair_mode=merged_wheelchair,
            frequent_places=merged_places,
            user_id=user_id,
        )
        logger.info("用户偏好已保存：session={}", session_id)
        return self._to_dict(pref)

    async def load_preferences(self, session_id: str) -> dict | None:
        """加载用户偏好。"""
        pref = await self._repo.get_by_session(session_id)
        if pref is None:
            return None
        return self._to_dict(pref)

    async def add_frequent_place(self, session_id: str, place: str, info: dict) -> dict | None:
        """添加常用地点到记忆。"""
        pref = await self._repo.get_by_session(session_id)
        if pref is None:
            pref = await self._repo.upsert_by_session(session_id)
        places = dict(pref.frequent_places or {})
        places[place] = info
        pref.frequent_places = places
        await self.db.flush()
        return self._to_dict(pref)

    async def clear_preferences(self, session_id: str) -> bool:
        """清除用户偏好（长期记忆清除）。"""
        pref = await self._repo.get_by_session(session_id)
        if pref is None:
            return False
        await self.db.delete(pref)
        await self.db.flush()
        logger.info("用户偏好已清除：session={}", session_id)
        return True

    @staticmethod
    def _to_dict(pref) -> dict:
        return {
            "id": pref.id,
            "session_id": pref.session_id,
            "font_size": pref.font_size,
            "speech_rate": pref.speech_rate,
            "language": pref.language,
            "high_contrast": pref.high_contrast,
            "wheelchair_mode": pref.wheelchair_mode,
            "frequent_places": pref.frequent_places or {},
        }


def get_memory_service(db: AsyncSession) -> MemoryService:
    return MemoryService(db)
