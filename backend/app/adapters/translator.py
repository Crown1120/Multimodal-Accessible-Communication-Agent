"""翻译适配器（中英互译）。

- TranslatorAdapter：统一接口
- MockTranslatorAdapter：基于词典的演示翻译
- OpenAITranslatorAdapter：基于 LLM 的翻译（复用 LLM 接口）

翻译适配器优先于 MCP 词典工具使用（当配置 API Key 时）。
"""

from __future__ import annotations

from typing import Protocol

from app.core.logging import get_logger

logger = get_logger()

# 公共服务高频词典（演示用）
_DICT_ZH_EN: dict[str, str] = {
    "骨科": "Orthopedics",
    "内科": "Internal Medicine",
    "儿科": "Pediatrics",
    "急诊": "Emergency Department",
    "妇产科": "Obstetrics and Gynecology",
    "挂号": "Registration",
    "身份证": "ID Card",
    "社保卡": "Social Security Card",
    "公积金": "Housing Provident Fund",
    "户口本": "Household Register",
    "请问": "Excuse me",
    "在哪里": "where is",
    "怎么办": "how to apply for",
    "怎么走": "how to get to",
    "无障碍": "accessibility",
    "服务台": "service desk",
    "一楼": "1st floor",
    "二楼": "2nd floor",
    "三楼": "3rd floor",
    "电梯": "elevator",
    "缴费": "payment",
    "取药": "pharmacy / medication pickup",
}


class TranslationResult:
    def __init__(self, text: str, *, source_lang: str, target_lang: str) -> None:
        self.text = text
        self.source_lang = source_lang
        self.target_lang = target_lang


class TranslatorAdapter(Protocol):
    async def translate(
        self, text: str, *, source_lang: str = "zh", target_lang: str = "en"
    ) -> TranslationResult: ...


class MockTranslatorAdapter:
    """词典式翻译，保证无 API Key 时演示可用。"""

    async def translate(
        self, text: str, *, source_lang: str = "zh", target_lang: str = "en"
    ) -> TranslationResult:
        if target_lang == "en":
            out = self._dict_translate(text, _DICT_ZH_EN)
        else:
            # 反向查表
            reverse = {v: k for k, v in _DICT_ZH_EN.items()}
            out = self._dict_translate(text, reverse)
        logger.info("Mock 翻译：{} -> {}", text, out)
        return TranslationResult(out, source_lang=source_lang, target_lang=target_lang)

    @staticmethod
    def _dict_translate(text: str, table: dict[str, str]) -> str:
        out = text
        for src, dst in table.items():
            out = out.replace(src, dst)
        return out


class OpenAITranslatorAdapter:
    """基于 LLM 的翻译（复用 LLM 适配器）。"""

    def __init__(self) -> None:
        from app.adapters.llm import get_llm_adapter

        self._llm = get_llm_adapter()

    async def translate(
        self, text: str, *, source_lang: str = "zh", target_lang: str = "en"
    ) -> TranslationResult:
        lang_name = "English" if target_lang == "en" else "Chinese"
        prompt = (
            f"Translate the following text to {lang_name}. "
            f"Only output the translation, no explanations.\n\n{text}"
        )
        messages = [
            {"role": "system", "content": "You are a professional translator for public service scenarios."},
            {"role": "user", "content": prompt},
        ]
        result = ""
        async for chunk in self._llm.stream_reply(messages):
            result += chunk
        return TranslationResult(result.strip(), source_lang=source_lang, target_lang=target_lang)


def get_translator_adapter() -> TranslatorAdapter:
    """根据配置返回适配器：有 LLM API Key 时用 LLM，否则降级词典。"""
    from app.core.config import settings

    if settings.llm_api_key:
        try:
            return OpenAITranslatorAdapter()
        except Exception as e:  # noqa: BLE001
            logger.warning("LLM 翻译适配器初始化失败，降级为词典：{}", e)
    return MockTranslatorAdapter()
