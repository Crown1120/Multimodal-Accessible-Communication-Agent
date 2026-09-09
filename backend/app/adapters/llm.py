"""LLM 适配器。

- LLMAdapter：统一接口（普通回复 + 流式回复）
- MockLLMAdapter：规则式回复，便于无 API Key 时演示核心闭环
- OpenAILLMAdapter：兼容 OpenAI Chat Completions（含流式）

外部服务不可用时降级到 Mock，保证闭环可演示。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from collections.abc import AsyncIterator
from typing import Protocol

from app.core.config import settings
from app.core.errors import AdapterError, ErrorCode
from app.core.http import get_http_client
from app.core.logging import get_logger

logger = get_logger()


class LLMAdapter(Protocol):
    """LLM 统一接口。

    注意 `stream_reply` 不是 `async def`：它是**异步生成器**，
    调用后直接返回 AsyncIterator（用 `async for` 消费）。
    声明成 `async def -> AsyncIterator` 会让类型检查器以为返回协程，
    从而无法校验适配器是否符合协议。
    """

    async def reply(self, messages: list[dict[str, str]]) -> str: ...

    def stream_reply(self, messages: list[dict[str, str]]) -> AsyncIterator[str]: ...

    async def classify_intent(self, text: str, *, scene: str = "hospital") -> str | None: ...


# 意图标签（与 graph 的节点路由保持一致）
INTENT_LABELS = ("knowledge", "chitchat", "route", "service", "translate", "privacy")

_INTENT_SYSTEM = (
    "你是公共服务无障碍沟通助手的意图分类器。"
    "把用户的问题归入以下之一，只输出 JSON，不要解释：\n"
    "- knowledge：咨询流程、政策、材料、费用等知识性问题\n"
    "- route：问路、带路、从某处到某处怎么走\n"
    "- service：查询某个服务点/窗口/科室的位置\n"
    "- translate：要求翻译或问某种语言怎么说\n"
    "- privacy：查询具体某位患者/他人的住院、床位、病情、检查结果\n"
    "- chitchat：寒暄、感谢、与业务无关的闲聊\n"
    '输出格式：{"intent": "<标签>"}'
)


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
        # 按块流式输出（不再逐字符 sleep 0.02s，避免人为拖慢响应）
        for i in range(0, len(text), 24):
            yield text[i : i + 24]

    async def classify_intent(self, text: str, *, scene: str = "hospital") -> str | None:
        """Mock 不提供意图分类，交由规则分类器处理。"""
        return None

    def _answer(self, user_text: str) -> str:
        kb = _HOSPITAL_KB if self.scene == "hospital" else _GOVERNMENT_KB
        for key, answer in kb.items():
            if key in user_text:
                return answer
        if self.scene == "hospital":
            return (
                "您好，这里是医院导诊。您可以告诉我需要找的科室（如骨科、内科）"
                "或业务（如挂号、无障碍服务），我来为您指引。"
            )
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

    @staticmethod
    def _cache_key(model: str, messages: list[dict[str, str]]) -> str:
        """缓存 key 覆盖完整输入（系统提示词含场景与 RAG 上下文 + 对话历史）。

        只按最后一条用户消息做 key 会让不同场景/上下文命中同一答案，属正确性 bug。
        """
        digest = hashlib.md5(json.dumps(messages, ensure_ascii=False).encode()).hexdigest()
        return f"{model}:{digest}"

    @staticmethod
    def _cache_put(key: str, reply: str) -> None:
        # 简单 LRU：超过上限时淘汰最早的一半
        if len(_llm_cache) >= _LLM_CACHE_MAX:
            for k in list(_llm_cache.keys())[: _LLM_CACHE_MAX // 2]:
                del _llm_cache[k]
        _llm_cache[key] = reply

    def _build_payload(self, messages: list[dict[str, str]], *, stream: bool) -> dict:
        payload: dict = {"model": self.model, "messages": messages, "stream": stream}
        # 限制输出长度，避免成本与延迟失控（导诊答复不需要长文）
        if settings.llm_max_tokens > 0:
            payload["max_tokens"] = settings.llm_max_tokens
        if settings.llm_temperature is not None:
            payload["temperature"] = settings.llm_temperature
        return payload

    async def reply(self, messages: list[dict[str, str]]) -> str:
        cache_key = self._cache_key(self.model, messages)
        if cache_key in _llm_cache:
            return _llm_cache[cache_key]
        data = await self._post(self._build_payload(messages, stream=False))
        reply = data["choices"][0]["message"]["content"]
        self._cache_put(cache_key, reply)
        return reply

    async def stream_reply(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        # 命中缓存时直接分块返回，避免重复调用 LLM（医院导诊高频问题命中率高）
        cache_key = self._cache_key(self.model, messages)
        cached = _llm_cache.get(cache_key)
        if cached is not None:
            for i in range(0, len(cached), 24):
                yield cached[i : i + 24]
            return

        payload = self._build_payload(messages, stream=True)
        client = get_http_client()
        collected: list[str] = []
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
                choices = obj.get("choices") or [{}]
                delta = (choices[0].get("delta") or {}).get("content")
                if delta:
                    collected.append(delta)
                    yield delta
        if collected:
            self._cache_put(cache_key, "".join(collected))

    async def classify_intent(self, text: str, *, scene: str = "hospital") -> str | None:
        """用 LLM 做意图分类（规则无法判定时的补充）。

        只输出一个短 JSON，`max_tokens` 很小，失败时返回 None 由调用方回退到规则结果。
        """
        if not text.strip():
            return None
        messages = [
            {"role": "system", "content": _INTENT_SYSTEM},
            {"role": "user", "content": f"场景：{scene}\n用户问题：{text}"},
        ]
        try:
            data = await self._post(
                {
                    "model": self.model,
                    "messages": messages,
                    "stream": False,
                    "max_tokens": 24,
                    "temperature": 0,
                }
            )
            content = data["choices"][0]["message"]["content"]
            match = re.search(r"\{.*\}", content, re.S)
            if not match:
                return None
            intent = json.loads(match.group(0)).get("intent")
        except Exception as e:  # noqa: BLE001
            logger.warning("LLM 意图分类失败，回退到规则：{}", e)
            return None
        return intent if intent in INTENT_LABELS else None

    async def _post(self, payload: dict) -> dict:
        client = get_http_client()
        last_error: Exception | None = None
        for attempt in range(settings.llm_max_retries + 1):
            if attempt:
                # 指数退避：0.5s, 1s, 2s...
                await asyncio.sleep(0.5 * (2 ** (attempt - 1)))
            try:
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
            except Exception as e:  # noqa: BLE001
                last_error = e
                logger.warning("LLM 请求异常（第 {} 次）：{}", attempt + 1, e)
                continue
            if resp.status_code == 200:
                return resp.json()
            # 4xx（除 429）不重试；5xx / 429 可重试
            if resp.status_code < 500 and resp.status_code != 429:
                raise AdapterError(
                    ErrorCode.ADAPTER_LLM_FAILED,
                    f"LLM 请求失败：HTTP {resp.status_code}",
                    details={"body": resp.text[:512]},
                )
            last_error = AdapterError(
                ErrorCode.ADAPTER_LLM_FAILED,
                f"LLM 请求失败：HTTP {resp.status_code}",
                details={"body": resp.text[:512]},
            )
            logger.warning("LLM 返回 {}，准备重试", resp.status_code)
        if isinstance(last_error, AdapterError):
            raise last_error
        raise AdapterError(
            ErrorCode.ADAPTER_LLM_FAILED,
            f"LLM 请求失败：{type(last_error).__name__ if last_error else 'unknown'}",
        )


def get_llm_adapter(scene: str = "hospital") -> LLMAdapter:
    """根据配置返回适配器：无 API Key 时降级为 Mock。"""
    if settings.llm_api_key:
        try:
            return OpenAILLMAdapter()
        except Exception as e:  # noqa: BLE001
            logger.warning("LLM 适配器初始化失败，降级为 Mock：{}", e)
    return MockLLMAdapter(scene=scene)
