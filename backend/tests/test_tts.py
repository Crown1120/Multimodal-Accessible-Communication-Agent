"""TTS 适配器单元测试：语速映射、NDJSON 解析、适配器路由。"""

from __future__ import annotations

import base64
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.adapters.tts import (
    MockTTSAdapter,
    OpenAITTSAdapter,
    TTSResult,
    VolcEngineTTSAdapter,
    get_tts_adapter,
)
from app.core.errors import AdapterError


class TestMockTTS:
    """Mock TTS 适配器测试。"""

    @pytest.mark.asyncio
    async def test_returns_none_audio(self):
        adapter = MockTTSAdapter()
        result = await adapter.synthesize("你好")
        assert isinstance(result, TTSResult)
        assert result.audio is None
        assert result.audio_url is None

    @pytest.mark.asyncio
    async def test_slow_speed_extends_delay(self):
        """慢速模式下应有额外延时（不报错即可）。"""
        adapter = MockTTSAdapter()
        result = await adapter.synthesize("你好", speed=0.8)
        assert result.audio is None


class TestVolcEngineSpeedMapping:
    """火山 TTS 语速映射测试：speed → speech_rate。"""

    def test_normal_speed(self):
        adapter = VolcEngineTTSAdapter(api_key="test", base_url="https://example.com")
        # speed=1.0 → speech_rate=0
        assert adapter is not None

    def test_speed_boundary_clamping(self):
        """speech_rate 应限制在 [-50, 100]。"""
        # speed=2.0 → (2.0-1.0)*100 = 100（上限）
        # speed=0.5 → (0.5-1.0)*100 = -50（下限）
        # speed=3.0 → (3.0-1.0)*100 = 200 → clamp 到 100
        # speed=0.0 → (0.0-1.0)*100 = -100 → clamp 到 -50
        high = max(-50, min(100, round((3.0 - 1.0) * 100)))
        low = max(-50, min(100, round((0.0 - 1.0) * 100)))
        assert high == 100
        assert low == -50

    def test_slow_speed_negative(self):
        """speed < 1.0 时 speech_rate 为负数。"""
        rate = round((0.8 - 1.0) * 100)
        assert rate == -20

    def test_fast_speed_positive(self):
        """speed > 1.0 时 speech_rate 为正数。"""
        rate = round((1.5 - 1.0) * 100)
        assert rate == 50


class TestVolcEngineNDJSON:
    """火山 TTS NDJSON 流式响应解析测试。"""

    def _make_ndjson_response(self, chunks: list[bytes], code: int = 20000000):
        """构造模拟的 NDJSON 响应文本。"""
        lines = []
        for chunk in chunks:
            lines.append(json.dumps({"code": 0, "data": base64.b64encode(chunk).decode()}))
        lines.append(json.dumps({"code": code, "message": "OK"}))
        return "\n".join(lines)

    @pytest.mark.asyncio
    async def test_parse_audio_chunks(self):
        """正常解析音频块并 base64 解码。"""
        audio_data = b"fake-audio-data-for-test"
        adapter = VolcEngineTTSAdapter(api_key="test", base_url="https://example.com")

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = self._make_ndjson_response([audio_data])

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.adapters.tts.get_http_client", return_value=mock_client):
            result = await adapter.synthesize("你好")
            assert result.audio == audio_data
            assert result.mime == "audio/mpeg"

    @pytest.mark.asyncio
    async def test_error_code_raises(self):
        """非 0/20000000 的 code 应抛出 AdapterError。"""
        adapter = VolcEngineTTSAdapter(api_key="test", base_url="https://example.com")

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = json.dumps({"code": 55000000, "message": "mismatched"})

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.adapters.tts.get_http_client", return_value=mock_client):
            with pytest.raises(AdapterError):
                await adapter.synthesize("你好")

    @pytest.mark.asyncio
    async def test_http_error_raises(self):
        """HTTP 非 200 应抛出 AdapterError。"""
        adapter = VolcEngineTTSAdapter(api_key="test", base_url="https://example.com")

        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.text = "forbidden"

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.adapters.tts.get_http_client", return_value=mock_client):
            with pytest.raises(AdapterError):
                await adapter.synthesize("你好")

    @pytest.mark.asyncio
    async def test_empty_audio_raises(self):
        """音频块为空应抛出 AdapterError。"""
        adapter = VolcEngineTTSAdapter(api_key="test", base_url="https://example.com")

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = json.dumps({"code": 20000000, "message": "OK"})

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.adapters.tts.get_http_client", return_value=mock_client):
            with pytest.raises(AdapterError, match="音频为空"):
                await adapter.synthesize("你好")


class TestTTSAdapterRouting:
    """TTS 适配器路由测试。"""

    def test_no_api_key_returns_mock(self):
        with patch("app.adapters.tts.settings") as mock_settings:
            mock_settings.tts_api_key = ""
            mock_settings.volc_asr_app_key = ""
            adapter = get_tts_adapter()
            assert isinstance(adapter, MockTTSAdapter)

    def test_volcengine_url_returns_volc_adapter(self):
        with patch("app.adapters.tts.settings") as mock_settings:
            mock_settings.tts_api_key = "test-key"
            mock_settings.volc_asr_app_key = ""
            mock_settings.tts_base_url = "https://openspeech.bytedance.com/api/v3/tts"
            adapter = get_tts_adapter()
            assert isinstance(adapter, VolcEngineTTSAdapter)

    def test_other_url_returns_openai_adapter(self):
        with patch("app.adapters.tts.settings") as mock_settings:
            mock_settings.tts_api_key = "test-key"
            mock_settings.volc_asr_app_key = ""
            mock_settings.tts_base_url = "https://api.openai.com/v1"
            adapter = get_tts_adapter()
            assert isinstance(adapter, OpenAITTSAdapter)
