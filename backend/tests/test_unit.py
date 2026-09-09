"""单元测试：意图路由、方言标准化、RAG 过滤、翻译、数字人动作、错误码。"""

from __future__ import annotations

import pytest

from app.adapters.digital_human import MinimalDigitalHumanAdapter
from app.adapters.translator import MockTranslatorAdapter
from app.agent.dialect import get_dialect_hints, normalize
from app.agent.graph import BridgeAgent
from app.core.errors import ErrorCode
from app.rag.store import _match, _to_chroma_where


class TestDialectPatternSafety:
    """方言映射表构建正则时的转义与顺序（回归：未转义会让元字符破坏匹配）。"""

    def test_metacharacters_are_escaped(self):
        import re

        from app.agent import dialect

        original = dict(dialect._DIALECT_MAP)
        try:
            dialect._DIALECT_MAP["C++"] = "编程语言"
            pattern = re.compile(
                "|".join(re.escape(k) for k in sorted(dialect._DIALECT_MAP, key=len, reverse=True))
            )
            assert pattern.search("我在学C++") is not None
        finally:
            dialect._DIALECT_MAP.clear()
            dialect._DIALECT_MAP.update(original)

    def test_longer_phrase_wins(self):
        from app.agent.dialect import normalize

        # “睇医生”比“医生”长，必须整体替换而不是部分替换
        assert normalize("我想睇医生") == "我想看医生"


class TestTTSCacheConsistency:
    """TTS 缓存与音频存储的一致性（回归：缓存命中但音频已被淘汰会返回死链）。"""

    @pytest.mark.asyncio
    async def test_evicted_audio_is_resynthesized(self):
        from app.adapters import digital_human
        from app.services.audio_store import audio_store

        class _FakeTTS:
            calls = 0

            async def synthesize(self, text, *, speed=1.0):
                from app.adapters.tts import TTSResult

                _FakeTTS.calls += 1
                return TTSResult(audio=b"fake-mp3", mime="audio/mpeg")

        adapter = digital_human.MinimalDigitalHumanAdapter()
        adapter._tts = _FakeTTS()
        digital_human._tts_cache.clear()
        try:
            first = await adapter.synthesize_audio("你好", speed=1.0)
            assert first is not None
            assert _FakeTTS.calls == 1

            # 清空音频存储，模拟 LRU 淘汰
            await audio_store.clear()

            second = await adapter.synthesize_audio("你好", speed=1.0)
            assert second is not None
            # 缓存里的 URL 已失效，必须重新合成而不是返回死链
            assert _FakeTTS.calls == 2
        finally:
            digital_human._tts_cache.clear()
            await audio_store.clear()


class TestAudioConversion:
    """音频转 WAV 的回归测试。

    回归背景：`_convert_with_pyav` 曾把 AudioFrame 直接传给 `mux()`，
    而 mux 需要的是 Packet，于是首选路径始终抛
    `TypeError: AudioFrame object is not iterable`，一直静默退到 ffmpeg 命令行
    （没有 ffmpeg 的环境则完全无法识别浏览器录音）。
    """

    @staticmethod
    def _make_wav(seconds: float = 0.2, rate: int = 16000) -> bytes:
        import io
        import struct
        import wave

        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(rate)
            wf.writeframes(
                b"".join(struct.pack("<h", int(1000 * ((i % 40) - 20) / 20)) for i in range(int(rate * seconds)))
            )
        return buf.getvalue()

    def test_pyav_conversion_produces_16k_mono_wav(self):
        pytest.importorskip("av")
        import os
        import shutil
        import tempfile
        import wave

        from app.adapters.asr import VoskASRAdapter

        tmpdir = tempfile.mkdtemp()
        try:
            out_path = os.path.join(tmpdir, "converted.wav")
            VoskASRAdapter._convert_with_pyav(self._make_wav(), out_path)

            with wave.open(out_path, "rb") as wf:
                assert wf.getframerate() == 16000
                assert wf.getnchannels() == 1
                assert wf.getsampwidth() == 2
                assert wf.getnframes() > 0
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_to_wav_falls_back_when_input_is_not_audio(self):
        """非音频字节不应抛裸异常，而应给出可读的 AdapterError。"""
        import os
        import shutil
        import tempfile

        from app.adapters.asr import VoskASRAdapter
        from app.core.errors import AdapterError

        adapter = VoskASRAdapter.__new__(VoskASRAdapter)  # 跳过模型加载
        tmpdir = tempfile.mkdtemp()
        try:
            with pytest.raises(AdapterError):
                path = await adapter._to_wav(b"not-a-real-audio-file")
                os.remove(path)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


class TestToolRegistryValidation:
    """工具层参数校验与白名单（回归：旧实现静默丢弃未知参数、不做类型校验）。"""

    def setup_method(self):
        from app.mcp.tools import register_all_tools

        register_all_tools()

    @pytest.mark.asyncio
    async def test_unknown_tool_rejected(self):
        from app.core.errors import ToolError
        from app.mcp.registry import registry

        with pytest.raises(ToolError, match="白名单"):
            await registry.call("drop_database", {})

    @pytest.mark.asyncio
    async def test_unknown_argument_rejected(self):
        from app.core.errors import ToolError
        from app.mcp.registry import registry

        with pytest.raises(ToolError, match="未知参数"):
            await registry.call("service_query", {"keyword": "骨科", "bogus": 1})

    @pytest.mark.asyncio
    async def test_wrong_argument_type_rejected(self):
        from app.core.errors import ToolError
        from app.mcp.registry import registry

        with pytest.raises(ToolError, match="参数类型错误"):
            await registry.call("service_query", {"keyword": 123})

    @pytest.mark.asyncio
    async def test_valid_call_succeeds(self):
        from app.mcp.registry import registry

        result = await registry.call("service_query", {"keyword": "骨科", "scene": "hospital"})
        assert result["tool"] == "service_query"
        assert result["widget"]["widget_type"] == "location"

    @pytest.mark.asyncio
    async def test_route_steps_skip_elevator_on_first_floor(self):
        """回归：一楼目的地不应提示「乘电梯到 1 楼」。"""
        from app.mcp.registry import registry

        result = await registry.call("route_query", {"destination": "急诊", "scene": "hospital"})
        steps = result["result"]["steps"]
        assert not any("电梯" in s for s in steps)


class TestDigitalHumanPayload:
    """数字人 speak 载荷构造（回归：不再猴子补丁私有 _tts）。"""

    def test_build_payload_has_no_audio_and_infers_mode(self):
        adapter = MinimalDigitalHumanAdapter()
        payload = adapter.build_speak_payload("您好，请到二楼骨科", mode="elderly")
        assert payload["audio_url"] is None
        assert payload["mode"] == "elderly"
        assert payload["speed"] < 1.0
        assert "repeat" in payload


class TestASRCooldown:
    """火山 ASR 降级冷却状态机回归测试（曾因缺 import time / 残留 _volc_status 崩溃）。"""

    def setup_method(self):
        from app.adapters import asr

        self.asr = asr
        asr._asr_adapter = None
        asr._asr_adapter_name = ""
        asr._clear_volc_cooldown()

    def teardown_method(self):
        self.asr._asr_adapter = None
        self.asr._clear_volc_cooldown()

    def test_cooldown_mark_and_clear_do_not_raise(self):
        # 回归：_mark_volc_cooldown 曾因未导入 time 抛 NameError
        assert self.asr._volc_in_cooldown() is False
        self.asr._mark_volc_cooldown(60.0)
        assert self.asr._volc_in_cooldown() is True
        self.asr._clear_volc_cooldown()
        assert self.asr._volc_in_cooldown() is False

    def test_get_adapter_skips_volc_during_cooldown(self):
        # 回归：get_asr_adapter 曾引用已删除的 _volc_status 抛 NameError
        from app.core.config import settings

        original_key = settings.volc_asr_app_key
        settings.volc_asr_app_key = "dummy-key-for-test"
        try:
            self.asr._mark_volc_cooldown(60.0)
            self.asr._asr_adapter = None
            adapter = self.asr.get_asr_adapter()
            assert adapter is not None
            # 冷却期内不应选中豆包云端适配器
            assert not isinstance(adapter, self.asr.VolcFlashASRAdapter)
        finally:
            settings.volc_asr_app_key = original_key
            self.asr._asr_adapter = None
            self.asr._clear_volc_cooldown()

    def test_cooldown_expiry_restores_volc(self, monkeypatch):
        from app.core.config import settings

        original_key = settings.volc_asr_app_key
        settings.volc_asr_app_key = "dummy-key-for-test"
        try:
            self.asr._mark_volc_cooldown(60.0)
            assert self.asr._volc_in_cooldown() is True
            # 模拟冷却到期
            monkeypatch.setattr(self.asr, "_volc_cooldown_until", 0.0)
            assert self.asr._volc_in_cooldown() is False
            self.asr._asr_adapter = None
            adapter = self.asr.get_asr_adapter()
            assert isinstance(adapter, self.asr.VolcFlashASRAdapter)
        finally:
            settings.volc_asr_app_key = original_key
            self.asr._asr_adapter = None
            self.asr._clear_volc_cooldown()


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
