"""LangGraph Agent：意图路由 -> RAG 检索 / MCP 工具 -> 回复生成。

LangGraph 不可用时回退到顺序节点执行，节点逻辑保持一致。
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from app.adapters.llm import get_llm_adapter
from app.agent.dialect import normalize as normalize_dialect
from app.agent.state import AgentState
from app.core.config import settings
from app.core.events import EventType, make_event
from app.core.logging import get_logger
from app.mcp.registry import registry
from app.mcp.tools import register_all_tools
from app.rag.retriever import get_rag
from app.repositories.tool_call_repo import record_tool_call
from app.services.event_bus import event_bus
from app.services.widget_store import widget_store

logger = get_logger()

# 已知地点关键词（用于意图路由与实体抽取）
_LOCATION_KEYWORDS = [
    "骨科", "内科", "儿科", "急诊", "妇产科", "挂号", "服务台",
    "户籍", "社保", "公积金", "户口",
]

# 明确路线/带路类触发词
_ROUTE_HINTS = (
    "怎么走", "怎么去", "路线", "从哪", "怎么到", "去哪",
    "带我去", "帮我去", "帮我找", "怎么找", "往哪", "指路", "怎么过去", "怎么走能到",
)
# 迷路/找不到类触发词（需同时含地点词才判为路线）
_NAV_HELP_HINTS = ("找不到", "迷路", "走丢", "找不到了", "不见了", "不知道怎么走")
_LOCATION_QUERY_HINTS = ("在哪", "几楼", "位置", "在哪儿", "在哪里", "在哪层", "在几楼")
_TRANSLATE_HINTS = ("翻译", "英语", "怎么说", "英文", "translate")

# 患者/他人隐私查询拦截：明确指向具体患者的住院、床位、病情等
_PRIVACY_STRONG = (
    "在哪个病房", "住哪个病房", "在几床", "几床", "床号", "住哪床", "在哪床",
    "哪个床位", "几号床", "床的患者", "床的病人",
    "病人在哪", "病人住哪", "患者在哪", "患者住哪", "病人是谁", "患者是谁",
    "病情怎么样", "检查结果怎么样", "诊断结果",
)
_PRIVACY_PERSON = (
    "爸爸", "妈妈", "爷爷", "奶奶", "外公", "外婆", "父亲", "母亲", "老伴",
    "儿子", "女儿", "孙子", "孙女", "哥哥", "姐姐", "弟弟", "妹妹",
    "老公", "老婆", "丈夫", "妻子", "朋友", "同事", "亲戚", "家属", "家人",
    "亲人", "患者", "病人", "舅舅", "姨妈", "叔叔", "姑姑", "表姐", "表哥",
    "我妈", "我爸", "我哥", "我姐", "我弟", "我妹", "我叔", "我舅", "我姑", "我姨",
    "我儿", "我女", "我孙", "我岳父", "我岳母", "我公婆",
)
_PRIVACY_WEAK = (
    "病房", "病情", "检查结果", "化验", "报告", "诊断", "情况", "在哪", "在哪里", "住哪", "几楼", "怎么样",
)
# 取件/领取语义：涉及「检查结果在哪拿」这类正当问路问题，不应判为隐私查询
_PICKUP_HINTS = (
    "在哪拿", "在哪取", "去哪里拿", "去哪里取", "怎么拿", "怎么取", "哪里领取", "怎么领取",
    "在哪领", "领取", "自助机", "打印报告", "取报告", "取结果", "拿报告", "拿结果",
)

# 隐私查询的固定拒绝话术（医院/政务通用口径）
_PRIVACY_REPLY = (
    "为了保护个人隐私，我不能查询或提供任何具体患者的住院信息、病房床位信息、"
    "病情或检查资料。如需联系住院患者，可以拨打医院总机转接，或到1楼服务台说明情况，"
    "由工作人员协助联系。感谢您的理解。"
)


# ---- 场景化系统提示词：让 Agent 回复贴合当前业务场景 ----
_SCENE_PROMPTS: dict[str, str] = {
    "hospital": (
        "你是医院导诊无障碍沟通助手 Bridge，服务对象是来院就诊的患者和家属，包含老年人、听障人士和行动不便者。\n"
        "你可以提供：挂号指引、科室与诊室位置、就诊和检查流程、缴费取药指引、无障碍服务（手语翻译志愿者、轮椅借用、实时字幕设备）。\n"
        "回复要求：语气温和耐心、口语化、尽量简短；先说清地点或流程结论，再补充必要细节；一次聚焦一件事，可分成步骤说明；当患者可能行动不便时，主动提示可用的无障碍服务。\n"
        "情感识别：当用户表达焦虑、紧张、痛苦、害怕等情绪时（如'我好害怕''很痛''怎么办''急死了'），先给予共情和安抚（如'我理解您的心情，请别着急'），再提供信息；语气要更加温和、缓慢，避免使用生硬的指令式语言。\n"
        "限制：不提供任何诊断、用药或治疗方案；科室位置拿不准时引导患者到一楼总服务台询问；"
        "危急优先：用户提及胸痛、呼吸困难、大出血、意识不清、严重外伤、疑似中风（口角歪斜/单侧无力/言语不清）、剧烈腹痛等危急症状时，第一句就要明确告知立即前往急诊科或拨打120，不要拖延、不要继续普通问答。"
        "隐私红线：严禁提供任何具体患者的个人信息、住院信息、病房床位信息、病情、检查结果或病历资料；"
        "凡涉及查询具体患者（含亲友）在哪个病房、几床、病情如何等问题，一律礼貌拒绝，并引导拨打医院总机转接或到服务台协助联系。"
    ),
    "government": (
        "你是政务服务大厅无障碍沟通助手 Bridge，服务对象是前来办事的群众，包含老年人、听障人士和行动不便者。\n"
        "你可以提供：身份证、社保、公积金、户口、不动产等业务的办理窗口、所需材料、办理流程与时限；叫号与排队引导；无障碍便利（优先叫号、手语翻译、字幕大屏）。\n"
        "回复要求：语气规范清晰又不失亲切、口语化；先说清办理地点和窗口，再说明材料和流程；分步骤说明；提醒老年人和残疾人可优先叫号。\n"
        "情感识别：当用户表达焦虑、着急、困惑等情绪时（如'怎么办''急死了''搞不懂'），先给予安抚（如'请别着急，我来帮您'），再提供信息；语气要更加耐心。\n"
        "限制：不承诺具体办理结果；办理时限和材料以窗口实际要求为准；不确定的业务引导群众到一楼导办台咨询。"
        "隐私红线：严禁提供任何个人的身份信息、办理记录或隐私资料；涉及查询他人信息（含亲友）一律礼貌拒绝，引导到窗口由工作人员按流程办理。"
    ),
}


async def _publish_widget(session_id: str, *, widget_id: str, widget_type: str, payload: dict) -> None:
    """下发 Widget：写入缓存（供回查）并推送 widget.show 事件。"""
    await widget_store.put(widget_id, widget_type=widget_type, payload=payload)
    await event_bus.publish(
        session_id,
        make_event(
            EventType.WIDGET_SHOW,
            session_id,
            0,
            widget_id=widget_id,
            widget_type=widget_type,
            payload=payload,
        ),
    )


def _build_scene_prompt(scene: str, rag_context: str = "", wheelchair: bool = False) -> str:
    """按场景构建系统提示词；无匹配场景时给出通用公共服务话术。"""
    sys = _SCENE_PROMPTS.get(
        scene,
        (
            "你是公共服务无障碍沟通助手 Bridge，服务对象包含老年人、听障人士和行动不便者。\n"
            "回复要求：语气温和、口语化、简短；先说结论再补充细节；分步骤说明；主动提供无障碍帮助。\n"
            "限制：只提供流程、地点和公开信息，不提供医疗诊断或处方。"
        ),
    )
    if wheelchair:
        sys += "\n\n轮椅模式：用户使用轮椅，所有路线指引必须优先选择无障碍通道（电梯、坡道、无障碍洗手间），避免楼梯和台阶；主动提示沿途无障碍设施位置。"
    if rag_context:
        sys += "\n\n参考知识（优先采用其中与本次问题相关的内容）：\n" + rag_context
    return sys


class BridgeAgent:
    """基于 LangGraph 的 Bridge Agent。"""

    def __init__(self) -> None:
        self._graph: Any = None
        # LangGraph 不可用（导入失败/编译失败）时置位，避免每次运行都重试构建
        self._graph_unavailable = False
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
        # 规则无法判定（落到 knowledge 兜底）时，用 LLM 再判一次；
        # 失败或超时则保持规则结果，保证主流程不受影响。
        if intent == "knowledge" and settings.llm_intent_enabled:
            refined = await self._llm_classify(text, state.get("scene", "hospital"))
            if refined:
                intent = refined
        await self._thinking(state, "route", f"识别意图：{intent}")
        return {"intent": intent}

    async def _llm_classify(self, text: str, scene: str) -> str | None:
        """LLM 意图分类（带超时与降级）。"""
        if len(text) < 4:
            return None
        try:
            adapter = get_llm_adapter(scene=scene)
            return await asyncio.wait_for(
                adapter.classify_intent(text, scene=scene),
                timeout=settings.llm_intent_timeout_seconds,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("LLM 意图分类异常，回退规则：{}", e)
            return None

    async def retrieve(self, state: AgentState) -> dict:
        sid = state["session_id"]
        await self._thinking(state, "retrieve", "检索知识库")
        rag = get_rag()
        res = await rag.retrieve_with_sources(
            state["user_text"], scene=state.get("scene"), language="zh", k=3
        )
        # 展示知识来源 Widget
        if res.get("sources"):
            await _publish_widget(
                sid,
                widget_id=f"src_{sid}",
                widget_type="knowledge_source",
                payload={"sources": res["sources"], "confident": res["confident"]},
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
        run_id = state.get("run_id") or ""
        tool_started = time.perf_counter()
        try:
            result = await registry.call(tool_name, args)
            await event_bus.publish(
                sid,
                make_event(EventType.TOOL_COMPLETED, sid, 0, tool=tool_name, result=result.get("result")),
            )
            # 持久化工具调用，便于审计与后续分析
            if run_id:
                await record_tool_call(
                    agent_run_id=run_id,
                    tool=tool_name,
                    args=args,
                    result=result.get("result"),
                    duration_ms=int((time.perf_counter() - tool_started) * 1000),
                )
            widget = result.get("widget")
            if widget:
                await _publish_widget(
                    sid,
                    widget_id=f"w_{sid}",
                    widget_type=widget["widget_type"],
                    payload=widget["payload"],
                )
            return {"tool_result": result.get("result"), "widget": widget}
        except Exception as e:  # noqa: BLE001
            logger.exception("工具调用失败")
            if run_id:
                await record_tool_call(
                    agent_run_id=run_id,
                    tool=tool_name,
                    args=args,
                    error_code="ERR_5004",
                    error_message=str(e)[:500],
                    duration_ms=int((time.perf_counter() - tool_started) * 1000),
                )
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

        # 0. 隐私查询：直接返回固定拒绝话术，不检索、不调工具
        if state.get("intent") == "privacy":
            async for ch in self._stream_text(_PRIVACY_REPLY):
                await event_bus.publish(
                    sid,
                    make_event(EventType.MESSAGE_DELTA, sid, 0, text=ch, role="assistant", run_id=state.get("run_id")),
                )
            return {"reply": _PRIVACY_REPLY}

        # 1. 工具结果可直接模板化为回复
        tool_result = state.get("tool_result")
        if tool_result and not tool_result.get("error"):
            text = self._render_tool_reply(tool_result, state.get("intent", ""), state.get("scene", "hospital"))
            async for ch in self._stream_text(text):
                await event_bus.publish(
                    sid,
                    make_event(EventType.MESSAGE_DELTA, sid, 0, text=ch, role="assistant", run_id=state.get("run_id")),
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
                    make_event(
                        EventType.MESSAGE_DELTA, sid, 0, text=chunk, role="assistant", run_id=state.get("run_id")
                    ),
                )
        except Exception as e:  # noqa: BLE001
            logger.exception("LLM 流式回复失败")
            full = "抱歉，回复生成出现异常，请稍后重试或到服务台寻求帮助。"
            await event_bus.publish(
                sid,
                make_event(
                    EventType.ERROR, sid, 0, code="ERR_6001", message="回复生成失败", details={"reason": str(e)}
                ),
            )
        return {"reply": full}

    # ---- 辅助 ----
    def _classify(self, text: str) -> str:
        if self._is_privacy_query(text):
            return "privacy"
        if any(h in text for h in _TRANSLATE_HINTS):
            return "translate"
        loc = next((k for k in _LOCATION_KEYWORDS if k in text), "")
        # 明确路线/带路类
        if any(h in text for h in _ROUTE_HINTS) or ("从" in text and "到" in text):
            return "route"
        # 找不到/迷路类（需含地点词，避免"找不到身份证"这类误判为导航）
        if loc and any(h in text for h in _NAV_HELP_HINTS):
            return "route"
        # 位置查询类
        if loc and any(h in text for h in _LOCATION_QUERY_HINTS):
            return "service"
        return "knowledge"

    @staticmethod
    def _is_privacy_query(text: str) -> bool:
        """是否涉及具体患者/他人的隐私查询（病房床位、病情、检查结果等）。

        注意误判：像「我妈的检查结果在哪拿」这类问「取件地点」的正当问题
        不应被拦截，因此先排除取件/领取语义。
        """
        if any(h in text for h in _PICKUP_HINTS):
            return False
        if any(h in text for h in _PRIVACY_STRONG):
            return True
        if any(p in text for p in _PRIVACY_PERSON) and any(w in text for w in _PRIVACY_WEAK):
            return True
        return False

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
        wheelchair = state.get("wheelchair", False)
        sys = _build_scene_prompt(scene, state.get("rag_context", ""), wheelchair=wheelchair)
        sys += "\n\n回复须简短、清晰、口语化的中文；只提供流程、地点和公开信息，不提供诊断或处方。"
        messages: list[dict[str, str]] = [{"role": "system", "content": sys}]
        for m in state.get("history", [])[-20:]:
            role = "user" if m.get("role") in ("user", "staff") else "assistant"
            messages.append({"role": role, "content": m.get("content", "")})
        messages.append({"role": "user", "content": state.get("user_text", "")})
        return messages

    @staticmethod
    def _render_tool_reply(tool_result: dict, intent: str, scene: str = "hospital") -> str:
        guide = "导办台" if scene == "government" else "服务台"
        if intent == "route" and "steps" in tool_result:
            steps = "，".join(tool_result["steps"])
            return f"为您规划了路线：{steps}。路线图已显示在画面中。"
        if "locations" in tool_result:
            locs = tool_result["locations"]
            if locs:
                first = locs[0]
                name = first.get("name", "该地点")
                floor = first.get("floor", "")
                area = first.get("area", "")
                direction = first.get("direction", "")
                return f"{name}在 {floor} 楼{area}（{direction}），详情见画面右下角。"
            return f"未找到相关服务点，请到一楼{guide}咨询。"
        if "result" in tool_result:  # translate
            return f"翻译结果：{tool_result['result']}"
        return "已为您查询到相关信息，详见右侧。"

    # 合成文本（工具结果 / 隐私话术）的分块大小。
    # 旧实现按「每字符 sleep 0.02s」伪造打字机效果：一条 200 字回复要多阻塞 4 秒，
    # 并产生 200 条 SSE 事件。改为按块推送、不 sleep，节奏交给前端渲染。
    _SYNTH_CHUNK = 24

    @staticmethod
    async def _stream_text(text: str):
        for i in range(0, len(text), BridgeAgent._SYNTH_CHUNK):
            yield text[i : i + BridgeAgent._SYNTH_CHUNK]

    async def _thinking(self, state: AgentState, step: str, detail: str) -> None:
        await event_bus.publish(
            state["session_id"],
            make_event(EventType.AGENT_THINKING, state["session_id"], 0, step=step, detail=detail),
        )

    # ---- 图构建与执行 ----
    def _build_graph(self) -> Any:
        """构建（并缓存）LangGraph 图；不可用时返回 None 表示走顺序回退。"""
        if self._graph is not None:
            return self._graph
        if self._graph_unavailable:
            return None
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
                    "privacy": "generate",
                },
            )
            g.add_edge("retrieve", "generate")
            g.add_edge("call_tool", "generate")
            g.add_edge("generate", END)
            self._graph = g.compile()
            logger.info("LangGraph Agent 已编译")
        except Exception as e:  # noqa: BLE001
            logger.warning("LangGraph 不可用，回退到顺序执行：{}", e)
            # 用独立标记代替「把 False 塞进 _graph」的哨兵写法
            self._graph_unavailable = True
            self._graph = None
        return self._graph

    async def run(self, state: AgentState) -> AgentState:
        graph = self._build_graph()
        if graph is None:
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
