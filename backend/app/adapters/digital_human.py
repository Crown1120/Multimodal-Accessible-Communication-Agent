"""数字人适配器（阶段4增强）。

阶段1：文本驱动，仅产出 digital_human.speak 事件（文本+情感）。
阶段3：接入 TTS、支持语速控制（老年模式慢速）、重要信息重复确认。
阶段4：表情、手势与动作元数据，驱动前端数字人肢体表现。
"""

from __future__ import annotations

from typing import Protocol

from app.core.config import settings
from app.core.logging import get_logger
from app.adapters.tts import TTSResult, get_tts_adapter

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
    async def speak(
        self,
        text: str,
        *,
        emotion: str | None = None,
        mode: str = "standard",
    ) -> dict: ...


class MinimalDigitalHumanAdapter:
    """最小数字人：根据内容推断情感与动作，结合 TTS 与模式自适应语速。"""

    def __init__(self) -> None:
        self._tts = get_tts_adapter()

    async def speak(
        self,
        text: str,
        *,
        emotion: str | None = None,
        mode: str = "standard",
    ) -> dict:
        if emotion is None:
            emotion = self._infer_emotion(text)

        # 根据模式决定语速
        speed = self._speed_for_mode(mode)

        # 重要信息重复确认（听障/老年模式）
        repeat = self._should_repeat(text, mode)

        # 推断手势动作与表情
        gesture = self._infer_gesture(text)
        expression = self._infer_expression(text)

        # TTS 合成（Mock 时返回 None，不阻断流程）
        audio_url = None
        try:
            tts_result = await self._tts.synthesize(text, speed=speed)
            if tts_result.audio:
                audio_url = "data:audio/mpeg;base64," + _to_b64(tts_result.audio)
        except Exception as e:  # noqa: BLE001
            logger.warning("TTS 合成失败，降级为纯文本播报：{}", e)

        payload: dict = {
            "text": text,
            "audio_url": audio_url,
            "emotion": emotion,
            "expression": expression,
            "gesture": gesture,
            "speed": speed,
            "mode": mode,
        }
        if repeat:
            payload["repeat"] = True
        return payload

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


def _to_b64(data: bytes) -> str:
    import base64

    return base64.b64encode(data).decode("ascii")


def get_digital_human_adapter() -> DigitalHumanAdapter:
    return MinimalDigitalHumanAdapter()
