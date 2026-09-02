"""用户偏好仓库。

对应开发文档第 7.4 节 Memory 服务：用户偏好持久化。
"""

from __future__ import annotations

import secrets

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db_models import UserPreference


def _new_id() -> str:
    return f"pref_{secrets.token_urlsafe(12)}"


class PreferenceRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_session(self, session_id: str) -> UserPreference | None:
        """按会话 ID 查询偏好。"""
        stmt = select(UserPreference).where(UserPreference.session_id == session_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_user(self, user_id: str) -> UserPreference | None:
        """按用户 ID 查询偏好。"""
        stmt = select(UserPreference).where(UserPreference.user_id == user_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert_by_session(
        self,
        session_id: str,
        *,
        font_size: str = "medium",
        speech_rate: str = "normal",
        language: str = "zh",
        high_contrast: bool = False,
        frequent_places: dict | None = None,
        user_id: str | None = None,
    ) -> UserPreference:
        """按会话 ID 创建或更新偏好。"""
        existing = await self.get_by_session(session_id)
        if existing:
            existing.font_size = font_size
            existing.speech_rate = speech_rate
            existing.language = language
            existing.high_contrast = high_contrast
            if frequent_places is not None:
                existing.frequent_places = frequent_places
            await self.db.flush()
            return existing

        pref = UserPreference(
            id=_new_id(),
            user_id=user_id,
            session_id=session_id,
            font_size=font_size,
            speech_rate=speech_rate,
            language=language,
            high_contrast=high_contrast,
            frequent_places=frequent_places or {},
        )
        self.db.add(pref)
        await self.db.flush()
        return pref
