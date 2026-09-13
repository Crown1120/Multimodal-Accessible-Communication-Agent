"""LLM 回复缓存：TTL 过期与主动清空。"""

from __future__ import annotations

import time

from app.adapters import llm
from app.adapters.llm import OpenAILLMAdapter, _cache_get, clear_llm_cache
from app.core.config import settings


def setup_function(_) -> None:
    llm._llm_cache.clear()


def test_cache_put_and_get() -> None:
    OpenAILLMAdapter._cache_put("k", "v")
    assert _cache_get("k") == "v"


def test_cache_expires_by_ttl(monkeypatch) -> None:
    monkeypatch.setattr(settings, "llm_cache_ttl_seconds", 10)
    # 直接写入一个已过期的时间戳
    llm._llm_cache["old"] = (time.time() - 999, "过期答案")
    assert _cache_get("old") is None
    assert "old" not in llm._llm_cache


def test_cache_ttl_zero_never_expires(monkeypatch) -> None:
    monkeypatch.setattr(settings, "llm_cache_ttl_seconds", 0)
    llm._llm_cache["old"] = (time.time() - 99999, "旧答案")
    assert _cache_get("old") == "旧答案"


def test_clear_llm_cache_returns_count() -> None:
    OpenAILLMAdapter._cache_put("a", "1")
    OpenAILLMAdapter._cache_put("b", "2")
    assert clear_llm_cache() == 2
    assert not llm._llm_cache
