"""方言语义标准化。

公共服务场景常见方言短语映射到标准中文，保证 RAG/工具可检索。
覆盖粤语、闽南语、吴语、四川话等高频公共服务用词。
"""

from __future__ import annotations

import re

from app.core.logging import get_logger

logger = get_logger()

# 方言 -> 标准中文 映射表（按场景聚合）
_DIALECT_MAP: dict[str, str] = {
    # 粤语
    "挂号": "挂号",
    "睇医生": "看医生",
    "边度": "哪里",
    "几多钱": "多少钱",
    "唔该": "麻烦/谢谢",
    "急诊室": "急诊",
    "骨科": "骨科",
    "点样去": "怎么走",
    "佢": "他",
    "我哋": "我们",
    # 闽南语
    "叨位": "哪里",
    "看医生": "看医生",
    "社仔": "社保",
    "按呢": "这样",
    # 吴语
    "啥地方": "哪里",
    "看毛病": "看病",
    "交关": "很/非常",
    # 四川话
    "搞快点": "快一点",
    "郎中": "医生",
    "堂客": "妻子",
    # 通用口语
    "咋个": "怎么",
    "啥子": "什么",
    "莫得": "没有",
    "要得": "好的",
    "不得行": "不行",
}

# 构建正则：按长度降序匹配，避免短串覆盖长串
_PATTERN = re.compile(
    "|".join(sorted(_DIALECT_MAP.keys(), key=len, reverse=True))
)


def normalize(text: str) -> str:
    """将方言短语替换为标准中文。

    返回标准化后的文本；未命中的原样保留。
    """
    if not text:
        return text

    def _replace(match: re.Match[str]) -> str:
        return _DIALECT_MAP[match.group(0)]

    normalized = _PATTERN.sub(_replace, text)
    if normalized != text:
        logger.info("方言标准化：{} -> {}", text, normalized)
    return normalized


def get_dialect_hints() -> list[dict[str, str]]:
    """返回方言映射表（供调试/展示用）。"""
    return [{"dialect": k, "standard": v} for k, v in _DIALECT_MAP.items()]
