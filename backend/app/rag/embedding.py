"""轻量中文嵌入（无外部依赖的回退方案）。

使用字符级 n-gram 词袋，便于中文语义近似匹配。
Chroma 后端可用时则使用其默认嵌入（ONNX MiniLM）。
"""

from __future__ import annotations

import math
import re
from collections import Counter
from unicodedata import normalize

_NG = 2  # 字符 bigram


def normalize_text(text: str) -> str:
    text = normalize("NFKC", text)
    text = re.sub(r"\s+", "", text)
    return text.lower()


def embed_text(text: str) -> Counter[str]:
    """将文本编码为字符 bigram 计数向量。"""
    text = normalize_text(text)
    if len(text) < _NG:
        return Counter({text: 1}) if text else Counter()
    return Counter(text[i : i + _NG] for i in range(len(text) - _NG + 1))


def cosine(a: Counter[str], b: Counter[str]) -> float:
    if not a or not b:
        return 0.0
    # 只在共同 key 上计算点积
    common = a & b  # Counter 交集取最小计数
    dot = sum(common.values())
    if dot == 0:
        return 0.0
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na and nb else 0.0
