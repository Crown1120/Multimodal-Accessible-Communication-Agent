"""LangGraph Agent：意图路由 -> RAG 检索 / MCP 工具 -> 回复生成。

LangGraph 不可用时回退到顺序节点执行，节点逻辑保持一致。
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

from app.adapters.llm import get_llm_adapter
from app.agent.dialect import normalize as normalize_dialect
from app.agent.state import AgentState
from app.core.events import EventType, make_event
from app.core.logging import get_logger
from app.mcp.registry import registry
from app.mcp.tools import register_all_tools
from app.rag.retriever import get_rag
from app.services.event_bus import event_bus

logger = get_logger()

# 已知地点关键词（用于意图路由与实体抽取）
_LOCATION_KEYWORDS = [
    "骨科", "内科", "儿科", "急诊", "妇产科", "挂号", "服务台",
    "户籍", "社保", "公积金", "户口",
]

_ROUTE_HINTS = ("怎么走", "怎么去", "路线", "从哪", "怎么到", "去哪")
_LOCATION_QUERY_HINTS = ("在哪", "几楼", "位置", "在哪儿", "在哪里", "在哪层")
_TRANSLATE_HINTS = ("翻译", "英语", "怎么说", "英文", "translate")


class BridgeAgent:
    """基于 LangGraph 的 Bridge Agent。"""

    def __init__(self) -> None:
        self._graph = None
        self._init_tools()

    def _init_tools(self) -> None:
        try:
            register_all_tools()
        except Exception as e:  # noqa: BLE001
            logger.warning("工具注册失败：{}", e)

    # ---- 节点 ----
    async def parse(self, state: AgentState) -> dict:
        user_text = state.get("user_text", "").strip()
        # 方言语义标准化（粤语/闽南语/吴语/四川话 -> 标准中文）
        user_text = normalize_dialect(user_text)
        await self._thinking(state, "parse", "解析用户输入")
        return {"user_text": user_text}

    async def route(self, state: AgentState) -> dict:
        text = state.get("user_text", "")
        intent = self._classify(text)
        await self._thinking(state, "route", f"识别意图：{intent}")
        return {"intent": intent}

    async def retrieve(self, state: AgentState) -> dict:
        sid = state["session_id"]
        await self._thinking(state, "retrieve", "检索知识库")
        rag = get_rag()
        res = await rag.retrieve_with_sources(
            state["user_text"], scene=state.get("scene"), language="zh", k=3
        )
        # 展示知识来源 Widget
        if res.get("sources"):
            await event_bus.publish(
                sid,
                make_event(
                    EventType.WIDGET_SHOW,
                    sid,
                    0,
                    widget_id=f"src_{sid}",
                    widget_type="knowledge_source",
                    payload={"sources": res["sources"], "confident": res["confident"]},
                ),
            )
        return {
            "rag_context": res.get("context", ""),
            "rag_sources": res.get("sources", []),
        }

    async def call_tool(self, state: AgentState) -> dict:
        sid = state["session_id"]
        intent = state.get("intent", "chitchat")
        text = state.get("user_text", "")
        scene = state.get("scene", "hospital")

        tool_name, args = self._select_tool(intent, text, scene)
        if not tool_name:
            return {"tool_result": None, "widget": None}

        await event_bus.publish(
            sid,
            make_event(EventType.TOOL_STARTED, sid, 0, tool=tool_name, args=args),
        )
        try:
            result = await registry.call(tool_name, args)
            await event_bus.publish(
                sid,
                make_event(EventType.TOOL_COMPLETED, sid, 0, tool=tool_name, result=result.get("result")),
            )
            widget = result.get("widget")
            if widget:
                await event_bus.publish(
                    sid,
                    make_event(
                        EventType.WIDGET_SHOW,
                        sid,
                        0,
                        widget_id=f"w_{sid}",
                        widget_type=widget["widget_type"],
                        payload=widget["payload"],
                    ),
                )
            return {"tool_result": result.get("result"), "widget": widget}
        except Exception as e:  # noqa: BLE001
            logger.exception("工具调用失败")
            await event_bus.publish(
                sid,
                make_event(
                    EventType.TOOL_FAILED,
                    sid,
                    0,
                    tool=tool_name,
                    code="ERR_5004",
                    message=str(e),
                ),
            )
            return {"tool_result": None, "widget": None, "error": str(e)}

    async def generate(self, state: AgentState) -> dict:
        sid = state["session_id"]
        await self._thinking(state, "generate", "生成回复")

        # 1. 工具结果可直接模板化为回复
        tool_result = state.get("tool_result")
        if tool_result and not tool_result.get("error"):
            text = self._render_tool_reply(tool_result, state.get("intent", ""))
            async for ch in self._stream_text(text):
                await event_bus.publish(
                    sid,
                    make_event(EventType.MESSAGE_DELTA, sid, 0, text=ch, role="assistant"),
                )
            return {"reply": text}

        # 2. 走 LLM（含 RAG 上下文）
        messages = self._build_messages(state)
        full = ""
        adapter = get_llm_adapter(scene=state.get("scene", "hospital"))
        try:
            async for chunk in adapter.stream_reply(messages):
                full += chunk
                await event_bus.publish(
                    sid,
                    make_event(EventType.MESSAGE_DELTA, sid, 0, text=chunk, role="assistant"),
                )
        except Exception as e:  # noqa: BLE001
            logger.exception("LLM 流式回复失败")
            full = "抱歉，回复生成出现异常，请稍后重试或到服务台寻求帮助。"
            await event_bus.publish(
                sid,
                make_event(EventType.ERROR, sid, 0, code="ERR_6001", message="回复生成失败", details={"reason": str(e)}),
            )
        return {"reply": full}

    # ---- 辅助 ----
    def _classify(self, text: str) -> str:
        if any(h in text for h in _TRANSLATE_HINTS):
            return "translate"
        if any(h in text for h in _ROUTE_HINTS) or ("从" in text and "到" in text):
            return "route"
        if any(loc in text for loc in _LOCATION_KEYWORDS) and any(
            h in text for h in _LOCATION_QUERY_HINTS
        ):
            return "service"
        return "knowledge"

    def _select_tool(self, intent: str, text: str, scene: str) -> tuple[str, dict]:
        location = next((k for k in _LOCATION_KEYWORDS if k in text), "")
        if intent == "translate":
            # 中文用户翻译请求默认目标为英文；明确要求中文时才翻译为中文
            target = "zh" if any(t in text for t in ("中文", "汉语", "chinese", "翻译成中文")) else "en"
            return "translate", {"text": text, "target_lang": target}
        if intent == "route":
            return "route_query", {"origin": "大厅入口", "destination": location or "服务台", "scene": scene}
        if intent == "service":
            return "service_query", {"keyword": location, "scene": scene}
        return "", {}

    def _build_messages(self, state: AgentState) -> list[dict[str, str]]:
        scene = state.get("scene", "hospital")
        sys = (
            "你是医院导诊无障碍沟通助手 Bridge。" if scene == "hospital"
            else "你是政务服务大厅无障碍沟通助手 Bridge。"
        )
        sys += "请用简短、清晰、口语化的中文回答。只提供流程、地点和公开信息，不提供诊断或处方。"
        ctx = state.get("rag_context", "")
        if ctx:
            sys += "\n\n参考知识：\n" + ctx
        messages: list[dict[str, str]] = [{"role": "system", "content": sys}]
        for m in state.get("history", [])[-20:]:
            role = "user" if m.get("role") in ("user", "staff") else "assistant"
            messages.append({"role": role, "content": m.get("content", "")})
        messages.append({"role": "user", "content": state.get("user_text", "")})
        return messages

    @staticmethod
    def _render_tool_reply(tool_result: dict, intent: str) -> str:
        if intent == "route" and "steps" in tool_result:
            steps = "，".join(tool_result["steps"])
            return f"为您规划了路线：{steps}。路线图已显示在右侧地图。"
        if "locations" in tool_result:
            locs = tool_result["locations"]
            if locs:
                first = locs[0]
                return f"{first.get('name', '该地点')}在 {first.get('floor', '')} 楼{first.get('area', '')}（{first.get('direction', '')}），详见右侧地点信息。"
            return "未找到相关服务点，请到服务台咨询。"
        if "result" in tool_result:  # translate
            return f"翻译结果：{tool_result['result']}"
        return "已为您查询到相关信息，详见右侧。"

    async def _stream_text(self, text: str):
        for ch in text:
            await asyncio.sleep(0.02)
            yield ch

    async def _thinking(self, state: AgentState, step: str, detail: str) -> None:
        await event_bus.publish(
            state["session_id"],
            make_event(EventType.AGENT_THINKING, state["session_id"], 0, step=step, detail=detail),
        )

    # ---- 图构建与执行 ----
    def _build_graph(self):
        if self._graph is not None:
            return self._graph
        try:
            from langgraph.graph import END, START, StateGraph

            g = StateGraph(AgentState)
            g.add_node("parse", self.parse)
            g.add_node("route", self.route)
            g.add_node("retrieve", self.retrieve)
            g.add_node("call_tool", self.call_tool)
            g.add_node("generate", self.generate)
            g.add_edge(START, "parse")
            g.add_edge("parse", "route")
            g.add_conditional_edges(
                "route",
                lambda s: s.get("intent", "knowledge"),
                {
                    "knowledge": "retrieve",
                    "chitchat": "generate",
                    "route": "call_tool",
                    "service": "call_tool",
                    "translate": "call_tool",
                },
            )
            g.add_edge("retrieve", "generate")
            g.add_edge("call_tool", "generate")
            g.add_edge("generate", END)
            self._graph = g.compile()
            logger.info("LangGraph Agent 已编译")
        except Exception as e:  # noqa: BLE001
            logger.warning("LangGraph 不可用，回退到顺序执行：{}", e)
            self._graph = False  # 标记使用回退
        return self._graph

    async def run(self, state: AgentState) -> AgentState:
        graph = self._build_graph()
        if graph is False:
            # 顺序回退
            state = {**state, **(await self.parse(state))}
            state = {**state, **(await self.route(state))}
            intent = state.get("intent", "knowledge")
            if intent == "knowledge":
                state = {**state, **(await self.retrieve(state))}
            elif intent in ("route", "service", "translate"):
                state = {**state, **(await self.call_tool(state))}
            state = {**state, **(await self.generate(state))}
            return state
        return await graph.ainvoke(state)


_agent: BridgeAgent | None = None


def get_agent() -> BridgeAgent:
    global _agent
    if _agent is None:
        _agent = BridgeAgent()
    return _agent
