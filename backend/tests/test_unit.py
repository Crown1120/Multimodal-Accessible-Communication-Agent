"""单元测试：意图路由、方言标准化、RAG 过滤、翻译、数字人动作、错误码。"""

from __future__ import annotations

import pytest

from app.agent.dialect import normalize, get_dialect_hints
from app.agent.graph import BridgeAgent
from app.adapters.digital_human import MinimalDigitalHumanAdapter
from app.adapters.translator import MockTranslatorAdapter
from app.core.errors import ErrorCode
from app.rag.store import _to_chroma_where, _match


class TestDialectNormalization:
    """方言标准化测试。"""

    def test_cantonese(self):
        assert normalize("睇医生") == "看医生"
        assert normalize("边度") == "哪里"

    def test_hokkien(self):
        assert normalize("叨位") == "哪里"

    def test_sichuan(self):
        assert normalize("啥子") == "什么"

    def test_no_dialect(self):
        assert normalize("请问骨科在哪里") == "请问骨科在哪里"

    def test_empty(self):
        assert normalize("") == ""

    def test_mixed(self):
        result = normalize("我想睇医生")
        assert "看医生" in result

    def test_hints(self):
        hints = get_dialect_hints()
        assert len(hints) > 0
        assert all("dialect" in h and "standard" in h for h in hints)


class TestIntentRouting:
    """意图路由测试。"""

    def setup_method(self):
        self.agent = BridgeAgent()

    def test_translate_intent(self):
        assert self.agent._classify("翻译骨科") == "translate"
        assert self.agent._classify("英文怎么说") == "translate"

    def test_route_intent(self):
        assert self.agent._classify("骨科怎么走") == "route"
        assert self.agent._classify("怎么去急诊") == "route"

    def test_service_intent(self):
        assert self.agent._classify("骨科在哪里") == "service"
        assert self.agent._classify("挂号几楼") == "service"

    def test_knowledge_intent(self):
        assert self.agent._classify("社保卡怎么办") == "knowledge"
        assert self.agent._classify("你好") == "knowledge"

    def test_tool_selection_translate(self):
        tool, args = self.agent._select_tool("translate", "翻译骨科", "hospital")
        assert tool == "translate"
        assert args["target_lang"] == "en"

    def test_tool_selection_route(self):
        tool, args = self.agent._select_tool("route", "骨科怎么走", "hospital")
        assert tool == "route_query"
        assert "骨科" in args["destination"]


class TestChromaWhere:
    """RAG 过滤条件转换测试。"""

    def test_none(self):
        assert _to_chroma_where(None) is None

    def test_single_key(self):
        result = _to_chroma_where({"language": "zh"})
        assert result == {"language": "zh"}

    def test_multiple_keys(self):
        result = _to_chroma_where({"language": "zh", "scene": "hospital"})
        assert "$and" in result
        assert len(result["$and"]) == 2

    def test_empty_dict(self):
        assert _to_chroma_where({}) is None

    def test_match(self):
        meta = {"language": "zh", "scene": "hospital"}
        assert _match(meta, {"language": "zh"}) is True
        assert _match(meta, {"language": "en"}) is False
        assert _match(meta, {"language": "zh", "scene": "hospital"}) is True
        assert _match(meta, {"language": "zh", "scene": "government"}) is False


class TestTranslation:
    """翻译适配器测试。"""

    @pytest.mark.asyncio
    async def test_zh_to_en(self):
        adapter = MockTranslatorAdapter()
        result = await adapter.translate("骨科", source_lang="zh", target_lang="en")
        assert "Orthopedics" in result.text
        assert result.source_lang == "zh"
        assert result.target_lang == "en"

    @pytest.mark.asyncio
    async def test_en_to_zh(self):
        adapter = MockTranslatorAdapter()
        result = await adapter.translate("Orthopedics", source_lang="en", target_lang="zh")
        assert "骨科" in result.text

    @pytest.mark.asyncio
    async def test_multi_word(self):
        adapter = MockTranslatorAdapter()
        result = await adapter.translate("请问骨科在哪里", source_lang="zh", target_lang="en")
        assert "Orthopedics" in result.text


class TestDigitalHuman:
    """数字人手势与表情测试。"""

    @pytest.mark.asyncio
    async def test_greeting_gesture(self):
        dh = MinimalDigitalHumanAdapter()
        payload = await dh.speak("您好！欢迎来到医院", mode="standard")
        assert payload["gesture"] == "wave"
        assert payload["expression"] == "smile"

    @pytest.mark.asyncio
    async def test_direction_gesture(self):
        dh = MinimalDigitalHumanAdapter()
        payload = await dh.speak("骨科在右侧电梯旁", mode="standard")
        assert payload["gesture"] == "point_right"

    @pytest.mark.asyncio
    async def test_apologetic(self):
        dh = MinimalDigitalHumanAdapter()
        payload = await dh.speak("抱歉，处理出现异常", mode="standard")
        assert payload["emotion"] == "apologetic"
        assert payload["gesture"] == "bow"

    @pytest.mark.asyncio
    async def test_hearing_mode_speed(self):
        dh = MinimalDigitalHumanAdapter()
        payload = await dh.speak("您好", mode="hearing")
        assert payload["speed"] == 0.9

    @pytest.mark.asyncio
    async def test_elderly_mode_speed(self):
        dh = MinimalDigitalHumanAdapter()
        payload = await dh.speak("您好", mode="elderly")
        assert payload["speed"] == 0.8

    @pytest.mark.asyncio
    async def test_repeat_important_info(self):
        dh = MinimalDigitalHumanAdapter()
        payload = await dh.speak("请到2楼骨科", mode="hearing")
        assert payload.get("repeat") is True

    @pytest.mark.asyncio
    async def test_no_repeat_standard_mode(self):
        dh = MinimalDigitalHumanAdapter()
        payload = await dh.speak("请到2楼骨科", mode="standard")
        assert "repeat" not in payload or payload["repeat"] is False


class TestErrorCodes:
    """错误码完整性测试。"""

    def test_error_code_format(self):
        for code in ErrorCode:
            assert code.value.startswith("ERR_")
            assert len(code.value) == 8

    def test_session_error(self):
        from app.core.errors import SessionError

        err = SessionError(ErrorCode.SESSION_NOT_FOUND, "测试")
        assert err.code == ErrorCode.SESSION_NOT_FOUND
        assert err.message == "测试"

    def test_adapter_error(self):
        from app.core.errors import AdapterError

        err = AdapterError(ErrorCode.ADAPTER_ASR_FAILED, "ASR失败", details={"k": "v"})
        assert err.code == ErrorCode.ADAPTER_ASR_FAILED
        assert err.details == {"k": "v"}
