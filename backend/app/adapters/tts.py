"""TTS（文字转语音）适配器。

- TTSAdapter：统一接口
- MockTTSAdapter：不生成真实音频，仅返回元数据（演示用）
- OpenAITTSAdapter：兼容 OpenAI TTS API，支持语速控制

老年模式通过 speed 参数实现慢速语音。
"""

from __future__ import annotations

import asyncio
from typing import Protocol

import httpx

from app.core.config import settings
from app.core.errors import AdapterError, ErrorCode
from app.core.logging import get_logger

logger = get_logger()


class TTSResult:
    """TTS 合成结果。"""

    def __init__(self, audio: bytes | None, *, audio_url: str | None = None, mime: str = "audio/mpeg") -> None:
        self.audio = audio
        self.audio_url = audio_url
        self.mime = mime


class TTSAdapter(Protocol):
    """TTS 统一接口。"""

    async def synthesize(
        self, text: str, *, speed: float = 1.0, voice: str | None = None
    ) -> TTSResult: ...


# ---- Mock 适配器（演示用，不生成真实音频）----
class MockTTSAdapter:
    """Mock TTS：仅返回元数据，保证无 API Key 时字幕与数字人闭环可演示。"""

    async def synthesize(
        self, text: str, *, speed: float = 1.0, voice: str | None = None
    ) -> TTSResult:
        await asyncio.sleep(0.05)  # 模拟合成延时
        # 慢速模式下适当延长，便于前端模拟播报节奏
        if speed < 1.0:
            await asyncio.sleep(0.1)
        logger.info("Mock TTS 合成（speed={}）：{}字", speed, len(text))
        return TTSResult(audio=None, audio_url=None)


# ---- OpenAI TTS 兼容适配器 ----
class OpenAITTSAdapter:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        voice: str | None = None,
    ) -> None:
        self.api_key = api_key or settings.tts_api_key
        self.base_url = (base_url or settings.tts_base_url).rstrip("/")
        self.model = model or settings.tts_model
        self.voice = voice or settings.tts_voice

    async def synthesize(
        self, text: str, *, speed: float = 1.0, voice: str | None = None
    ) -> TTSResult:
        # OpenAI TTS speed 范围 0.25-4.0
        speed = max(0.25, min(4.0, speed))
        payload = {
            "model": self.model,
            "input": text,
            "voice": voice or self.voice,
            "response_format": "mp3",
            "speed": speed,
        }
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{self.base_url}/audio/speech",
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            if resp.status_code != 200:
                raise AdapterError(
                    ErrorCode.ADAPTER_TTS_FAILED,
                    f"TTS 请求失败：HTTP {resp.status_code}",
                    details={"body": resp.text[:512]},
                )
            return TTSResult(audio=resp.content, mime="audio/mpeg")


def get_tts_adapter() -> TTSAdapter:
    """根据配置返回适配器：无 API Key 时降级为 Mock。"""
    if settings.tts_api_key:
        try:
            return OpenAITTSAdapter()
        except Exception as e:  # noqa: BLE001
            logger.warning("TTS 适配器初始化失败，降级为 Mock：{}", e)
    return MockTTSAdapter()
