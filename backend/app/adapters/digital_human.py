"""数字人适配器（阶段4增强）。

阶段1：文本驱动，仅产出 digital_human.speak 事件（文本+情感）。
阶段3：接入 TTS、支持语速控制（老年模式慢速）、重要信息重复确认。
阶段4：表情、手势与动作元数据，驱动前端数字人肢体表现。
"""

from __future__ import annotations

from typing import Protocol

from app.adapters.tts import get_tts_adapter
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger()


# 需要重复确认的关键信息关键词
_IMPORTANT_KEYWORDS = (
    "科室", "窗口", "楼层", "几楼", "楼", "需要", "请带", "工本费",
    "工作日", "身份证", "社保卡", "医保卡", "户口本",
)

# 老年模式语速
_ELDERLY_SPEED = 0.8
# 听障模式语速（更慢，便于阅读字幕同步）
_HEARING_SPEED = 0.9

# 动作映射：内容关键词 -> 数字人肢体动作
_GESTURE_MAP: list[tuple[str, str]] = [
    ("您好", "wave"),           # 挥手问候
    ("欢迎", "wave"),
    ("请", "gesture_open"),    # 手势引导
    ("这边", "point_right"),   # 指引方向
    ("右侧", "point_right"),
    ("左侧", "point_left"),
    ("左边", "point_left"),
    ("东侧", "point_right"),
    ("西侧", "point_left"),
    ("上楼", "point_up"),      # 指引上楼
    ("下楼", "point_down"),
    ("电梯", "point_up"),
    ("几楼", "point_up"),
    ("抱歉", "bow"),           # 鞠躬致歉
    ("请稍候", "think"),       # 思考等待
    ("路线", "point_right"),   # 指引路线
    ("到达", "gesture_open"),
    ("注意", "raise_hand"),   # 举手提示
    ("重要", "raise_hand"),
]

# 表情映射
_EXPRESSION_MAP: list[tuple[str, str]] = [
    ("您好", "smile"),
    ("欢迎", "smile"),
    ("抱歉", "apologetic"),
    ("失败", "sad"),
    ("异常", "sad"),
    ("恭喜", "happy"),
    ("注意", "serious"),
    ("重要", "serious"),
]


class SpeakPayload(dict):
    """digital_human.speak 事件载荷（dict 子类，便于 ** 展开）。"""


class DigitalHumanAdapter(Protocol):
    """数字人统一接口。

    runner 会用到 `build_speak_payload`（先推文本再异步合成音频）与
    `synthesize_audio`，此前协议里没有声明这两个方法，
    导致类型检查无法发现适配器实现缺失。
    """

    def build_speak_payload(
        self,
        text: str,
        *,
        emotion: str | None = None,
        mode: str = "standard",
    ) -> dict: ...

    async def speak(
        self,
        text: str,
        *,
        emotion: str | None = None,
        mode: str = "standard",
    ) -> dict: ...

    async def synthesize_audio(self, text: str, *, speed: float = 1.0) -> str | None: ...


class MinimalDigitalHumanAdapter:
    """最小数字人：根据内容推断情感与动作，结合 TTS 与模式自适应语速。"""

    def __init__(self) -> None:
        self._tts = get_tts_adapter()

    def build_speak_payload(
        self,
        text: str,
        *,
        emotion: str | None = None,
        mode: str = "standard",
    ) -> dict:
        """构造不含音频的 speak 载荷（纯函数，不做任何 IO）。

        原实现在 runner 里通过临时把 `_tts` 换成 Noop 来复用这段推断逻辑，
        属于对私有属性的猴子补丁；这里显式暴露为方法，语义更清晰也不会
        在多协程下互相干扰。
        """
        if emotion is None:
            emotion = self._infer_emotion(text)
        payload: dict = {
            "text": text,
            "audio_url": None,
            "emotion": emotion,
            "expression": self._infer_expression(text),
            "gesture": self._infer_gesture(text),
            "speed": self._speed_for_mode(mode),
            "mode": mode,
        }
        if self._should_repeat(text, mode):
            payload["repeat"] = True
        return payload

    async def speak(
        self,
        text: str,
        *,
        emotion: str | None = None,
        mode: str = "standard",
    ) -> dict:
        payload = self.build_speak_payload(text, emotion=emotion, mode=mode)

        # TTS 合成（Mock 时返回 None，不阻断流程）
        try:
            tts_result = await self._tts.synthesize(text, speed=payload["speed"])
            if tts_result.audio:
                payload["audio_url"] = await _store_audio(tts_result.audio, tts_result.mime)
        except Exception as e:  # noqa: BLE001
            logger.warning("TTS 合成失败，降级为纯文本播报：{}", e)

        return payload

    async def synthesize_audio(self, text: str, *, speed: float = 1.0) -> str | None:
        """仅合成音频，返回音频访问 URL（用于异步 TTS，先推送文本再推送音频）。
        相同文本+语速命中缓存时直接返回，避免重复合成。

        返回形如 `/api/audio/{audio_id}` 的短路径，而不是 base64 data URL——
        避免 SSE 帧膨胀与事件重放缓冲长期持有音频。
        """
        cache_key = f"{speed}:{text}"
        cached = _tts_cache.get(cache_key)
        if cached is not None:
            # 音频存储容量比 TTS 缓存小，命中缓存不代表音频还在——
            # 直接返回已被淘汰的 URL 会让前端拿到 404、数字人静音。
            if await _audio_exists(cached):
                return cached
            _tts_cache.pop(cache_key, None)
        try:
            tts_result = await self._tts.synthesize(text, speed=speed)
            if tts_result.audio:
                audio_url = await _store_audio(tts_result.audio, tts_result.mime)
                # 简单 LRU：超过上限时淘汰最早的一半
                if len(_tts_cache) >= _TTS_CACHE_MAX:
                    for k in list(_tts_cache.keys())[: _TTS_CACHE_MAX // 2]:
                        del _tts_cache[k]
                _tts_cache[cache_key] = audio_url
                return audio_url
        except Exception as e:  # noqa: BLE001
            logger.warning("异步 TTS 合成失败：{}", e)
        return None

    @staticmethod
    def _speed_for_mode(mode: str) -> float:
        if mode == "elderly":
            return _ELDERLY_SPEED
        if mode == "hearing":
            return _HEARING_SPEED
        return settings.tts_speed

    @staticmethod
    def _should_repeat(text: str, mode: str) -> bool:
        """听障/老年模式下，关键信息需要重复确认。"""
        if mode not in ("hearing", "elderly"):
            return False
        return any(kw in text for kw in _IMPORTANT_KEYWORDS)

    @staticmethod
    def _infer_emotion(text: str) -> str:
        if any(w in text for w in ("抱歉", "失败", "异常", "错误")):
            return "apologetic"
        if any(w in text for w in ("您好", "欢迎", "请")):
            return "friendly"
        return "neutral"

    @staticmethod
    def _infer_gesture(text: str) -> str:
        for keyword, gesture in _GESTURE_MAP:
            if keyword in text:
                return gesture
        return "idle"

    @staticmethod
    def _infer_expression(text: str) -> str:
        for keyword, expression in _EXPRESSION_MAP:
            if keyword in text:
                return expression
        return "neutral"


# TTS 音频缓存：相同文本+语速不重复合成（医院导诊高频问题命中率高）
_tts_cache: dict[str, str] = {}
_TTS_CACHE_MAX = 200


async def _store_audio(data: bytes, mime: str) -> str:
    """把音频存入 audio_store，返回可访问的短 URL。"""
    from app.services.audio_store import audio_store

    audio_id = await audio_store.put(data, mime=mime)
    return f"/api/audio/{audio_id}"


async def _audio_exists(audio_url: str) -> bool:
    """缓存里的 URL 对应音频是否仍在存储中。"""
    from app.services.audio_store import audio_store

    audio_id = audio_url.rsplit("/", 1)[-1]
    return await audio_store.get(audio_id) is not None


def get_digital_human_adapter() -> DigitalHumanAdapter:
    return MinimalDigitalHumanAdapter()
