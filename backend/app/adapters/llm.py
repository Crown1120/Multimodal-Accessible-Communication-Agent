"""LLM 适配器。

- LLMAdapter：统一接口（普通回复 + 流式回复）
- MockLLMAdapter：规则式回复，便于无 API Key 时演示核心闭环
- OpenAILLMAdapter：兼容 OpenAI Chat Completions（含流式）

外部服务不可用时降级到 Mock，保证闭环可演示。
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Protocol

import httpx

from app.core.config import settings
from app.core.errors import AdapterError, ErrorCode
from app.core.logging import get_logger

logger = get_logger()


class LLMAdapter(Protocol):
    async def reply(self, messages: list[dict[str, str]]) -> str: ...

    async def stream_reply(self, messages: list[dict[str, str]]) -> AsyncIterator[str]: ...


# ---- Mock 适配器（演示用，按关键词命中内置话术）----
_HOSPITAL_KB = {
    "骨科": "骨科在门诊二楼外科区域，沿主走廊东侧到头即可到达。",
    "内科": "内科在一楼门诊大厅北侧，包括心内科、呼吸内科、消化内科和神经内科。",
    "儿科": "儿科在一楼东区，分普通儿科和儿童保健。",
    "急诊": "急诊在一楼西侧，24 小时接诊。",
    "妇产科": "妇产科在三楼，包含产科门诊和妇科门诊。",
    "挂号": "挂号可到一楼人工窗口或自助机，也可线上预约；建议带身份证和医保卡。",
    "无障碍": "一楼总服务台配备手语翻译志愿者（工作日 9:00-17:00），可借用实时字幕设备和轮椅。",
}
_GOVERNMENT_KB = {
    "身份证": "身份证办理到户籍窗口，工本费 20 元，15 个工作日领取，请带旧证或户口本。",
    "社保": "社保卡申领到社保窗口，现场拍照，7 个工作日领取。",
    "公积金": "公积金查询到公积金窗口，凭身份证即可办理。",
    "户口": "户口迁移到户籍窗口，需提供原户籍证明。",
    "无障碍": "一楼导办台有手语翻译志愿者（工作日 9:00-17:00），全厅覆盖实时字幕大屏，老年人和残疾人可优先叫号。",
}


class MockLLMAdapter:
    """规则式 LLM，保证无 API Key 时核心闭环可演示。"""

    def __init__(self, scene: str = "hospital") -> None:
        self.scene = scene

    async def reply(self, messages: list[dict[str, str]]) -> str:
        await asyncio.sleep(0.1)  # 模拟思考延时
        user_text = messages[-1].get("content", "") if messages else ""
        return self._answer(user_text)

    async def stream_reply(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        text = self._answer(messages[-1].get("content", "") if messages else "")
        # 按字符流式输出，前端拼装 message.delta
        for ch in text:
            await asyncio.sleep(0.02)
            yield ch

    def _answer(self, user_text: str) -> str:
        kb = _HOSPITAL_KB if self.scene == "hospital" else _GOVERNMENT_KB
        for key, answer in kb.items():
            if key in user_text:
                return answer
        if self.scene == "hospital":
            return "您好，这里是医院导诊。您可以告诉我需要找的科室（如骨科、内科）或业务（如挂号、无障碍服务），我来为您指引。"
        return "您好，这里是政务服务大厅。您可以告诉我办理业务（如身份证、社保、公积金），我来为您说明流程。"


# ---- OpenAI 兼容适配器 ----
# LLM 回复缓存：相同用户问题不重复调用 LLM（医院导诊高频问题命中率高）
_llm_cache: dict[str, str] = {}
_LLM_CACHE_MAX = 100


class OpenAILLMAdapter:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        self.api_key = api_key or settings.llm_api_key
        self.base_url = (base_url or settings.llm_base_url).rstrip("/")
        self.model = model or settings.llm_model

    async def reply(self, messages: list[dict[str, str]]) -> str:
        # 缓存 key：模型 + 最后一条用户消息（医院导诊场景相同问题回复相同）
        user_msg = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
        cache_key = f"{self.model}:{user_msg}"
        if cache_key in _llm_cache:
            return _llm_cache[cache_key]
        payload = {"model": self.model, "messages": messages, "stream": False}
        data = await self._post(payload)
        reply = data["choices"][0]["message"]["content"]
        # 简单 LRU：超过上限时淘汰最早的一半
        if len(_llm_cache) >= _LLM_CACHE_MAX:
            for k in list(_llm_cache.keys())[: _LLM_CACHE_MAX // 2]:
                del _llm_cache[k]
        _llm_cache[cache_key] = reply
        return reply

    async def stream_reply(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        payload = {"model": self.model, "messages": messages, "stream": True}
        async with httpx.AsyncClient(timeout=60) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}"},
            ) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    raise AdapterError(
                        ErrorCode.ADAPTER_LLM_FAILED,
                        f"LLM 请求失败：HTTP {resp.status_code}",
                        details={"body": body.decode(errors="ignore")[:512]},
                    )
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    chunk = line[5:].strip()
                    if chunk == "[DONE]":
                        break
                    try:
                        obj = json.loads(chunk)
                    except json.JSONDecodeError:
                        continue
                    delta = obj.get("choices", [{}])[0].get("delta", {}).get("content")
                    if delta:
                        yield delta

    async def _post(self, payload: dict) -> dict:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            if resp.status_code != 200:
                raise AdapterError(
                    ErrorCode.ADAPTER_LLM_FAILED,
                    f"LLM 请求失败：HTTP {resp.status_code}",
                    details={"body": resp.text[:512]},
                )
            return resp.json()


def get_llm_adapter(scene: str = "hospital") -> LLMAdapter:
    """根据配置返回适配器：无 API Key 时降级为 Mock。"""
    if settings.llm_api_key:
        try:
            return OpenAILLMAdapter()
        except Exception as e:  # noqa: BLE001
            logger.warning("LLM 适配器初始化失败，降级为 Mock：{}", e)
    return MockLLMAdapter(scene=scene)
