"""TTS（文字转语音）适配器。

- TTSAdapter：统一接口
- MockTTSAdapter：不生成真实音频，仅返回元数据（演示用）
- VolcEngineTTSAdapter：火山引擎/豆包 SeedTTS 2.0 单向流式 HTTP（新版控制台 X-Api-Key 鉴权）
- OpenAITTSAdapter：兼容 OpenAI TTS API（备用）

老年/听障模式通过 speed 参数实现慢速语音。
"""

from __future__ import annotations

import asyncio
import base64
import json
import uuid
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


# ---- 火山引擎 / 豆包 SeedTTS 2.0 单向流式 HTTP 适配器 ----
class VolcEngineTTSAdapter:
    """豆包语音合成大模型2.0（SeedTTS 2.0）单向流式 HTTP 适配器。

    协议：POST {base}/unidirectional
    鉴权：新版控制台 X-Api-Key（无需 APP Secret / token，ASR 与 TTS 共用同一把 Key）
    参考：https://docs.volcengine.com/docs/6561/2528925
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        resource_id: str | None = None,
        voice: str | None = None,
    ) -> None:
        # TTS_API_KEY 为空时自动复用火山 ASR 的 APP Key（config 已做同步，这里再兜底）
        self.api_key = api_key or settings.tts_api_key or settings.volc_asr_app_key
        self.base_url = (base_url or settings.tts_base_url).rstrip("/")
        self.resource_id = resource_id or settings.tts_seedtts_resource_id or "seed-tts-2.0"
        self.voice = voice or settings.tts_voice

    async def synthesize(
        self, text: str, *, speed: float = 1.0, voice: str | None = None
    ) -> TTSResult:
        # speech_rate 取值范围 [-50, 100]：100=2.0 倍速，-50=0.5 倍速
        speech_rate = max(-50, min(100, round((speed - 1.0) * 100)))
        payload = {
            "req_params": {
                "text": text,
                "speaker": voice or self.voice,
                "audio_params": {
                    "format": "mp3",
                    "sample_rate": 24000,
                    "speech_rate": speech_rate,
                },
            }
        }
        headers = {
            "X-Api-Key": self.api_key,
            "X-Api-Resource-Id": self.resource_id,
            "X-Api-Request-Id": str(uuid.uuid4()),
            "X-Control-Require-Usage-Tokens-Return": "*",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{self.base_url}/unidirectional",
                json=payload,
                headers=headers,
            )
            if resp.status_code != 200:
                detail = resp.text[:512]
                try:
                    err = resp.json()
                    msg = err.get("header", {}).get("message") or err.get("message") or ""
                except Exception:  # noqa: BLE001
                    msg = ""
                raise AdapterError(
                    ErrorCode.ADAPTER_TTS_FAILED,
                    f"TTS 请求失败：HTTP {resp.status_code}"
                    + (f"（{msg}）" if msg else ""),
                    details={"body": detail},
                )
            # 单向流式返回 NDJSON（每行一个 JSON 块），逐行解析并拼接音频
            audio_chunks: list[str] = []
            last_code = 0
            last_msg = ""
            for line in resp.text.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue
                code = chunk.get("code", 0)
                # 0 = 音频/元数据块；20000000 OK = 流式成功结束标记
                if code not in (0, 20000000):
                    last_code = code
                    last_msg = chunk.get("message", "")
                    break
                if chunk.get("data"):
                    audio_chunks.append(chunk["data"])
            if last_code != 0:
                raise AdapterError(
                    ErrorCode.ADAPTER_TTS_FAILED,
                    f"TTS 合成失败：{last_msg or '未知错误'}（code={last_code}）",
                )
            if not audio_chunks:
                raise AdapterError(ErrorCode.ADAPTER_TTS_FAILED, "TTS 返回音频为空")
            audio = base64.b64decode("".join(audio_chunks))
            return TTSResult(audio=audio, mime="audio/mpeg")


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
    """根据配置返回适配器：无 API Key 时降级为 Mock。

    火山语音（TTS_BASE_URL 含 openspeech.bytedance.com）→ VolcEngineTTSAdapter；
    其他 → OpenAI 兼容适配器。
    """
    api_key = settings.tts_api_key or settings.volc_asr_app_key
    if not api_key:
        return MockTTSAdapter()
    try:
        base_url = (settings.tts_base_url or "").lower()
        if "openspeech.bytedance.com" in base_url:
            return VolcEngineTTSAdapter(api_key=api_key)
        return OpenAITTSAdapter(api_key=api_key)
    except Exception as e:  # noqa: BLE001
        logger.warning("TTS 适配器初始化失败，降级为 Mock：{}", e)
    return MockTTSAdapter()
