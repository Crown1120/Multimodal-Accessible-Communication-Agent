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


def dot(a: Counter[str], b: Counter[str]) -> float:
    """只在共同 key 上计算点积（Counter 交集取最小计数）。"""
    return float(sum((a & b).values()))


def vector_norm(vec: Counter[str]) -> float:
    """向量模长。文档向量可预计算，避免每次查询重复计算。"""
    return math.sqrt(sum(v * v for v in vec.values()))


def cosine(a: Counter[str], b: Counter[str]) -> float:
    if not a or not b:
        return 0.0
    na = vector_norm(a)
    nb = vector_norm(b)
    if not na or not nb:
        return 0.0
    return dot(a, b) / (na * nb)
