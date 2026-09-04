"""ASR（语音转文字）适配器。

- ASRAdapter：统一接口（整体转写 + 流式增量转写）
- VolcFlashASRAdapter：豆包大模型极速版 HTTP ASR（云端高精度）
- OpenAIASRAdapter：兼容 OpenAI Whisper API
- WhisperASRAdapter：faster-whisper 离线高精度（small 约 244MB）
- VoskASRAdapter：Vosk 离线中文小模型（40MB，兜底）
- MockASRAdapter：规则式转写，便于无 API Key 时演示核心闭环

外部服务不可用时逐级降级，保证闭环可演示。
"""

from __future__ import annotations

import base64
import uuid as _uuid

import asyncio
import re
from collections.abc import AsyncIterator
from typing import Protocol

import httpx

from app.core.config import settings
from app.core.errors import AdapterError, ErrorCode
from app.core.logging import get_logger

logger = get_logger()


class ASRResult:
    """ASR 转写结果。"""

    def __init__(self, text: str, *, language: str = "zh", confidence: float = 1.0) -> None:
        self.text = text
        self.language = language
        self.confidence = confidence


class ASRAdapter(Protocol):
    """ASR 统一接口。"""

    async def transcribe(self, audio: bytes, *, language: str = "zh") -> ASRResult: ...

    async def stream_transcribe(
        self, audio: bytes, *, language: str = "zh"
    ) -> AsyncIterator[str]: ...


# ---- Mock 适配器（演示用，返回固定话术）----
_MOCK_PHRASES = [
    "请问骨科在哪里",
    "我想挂号",
    "急诊怎么走",
    "身份证怎么办理",
    "无障碍服务在哪里",
    "社保卡怎么申领",
]


class MockASRAdapter:
    """规则式 ASR，保证无 API Key 时核心闭环可演示。

    根据音频字节数稳定选一句演示话术，避免随机导致难以复现。
    """

    def __init__(self, language: str = "zh") -> None:
        self.language = language

    async def transcribe(self, audio: bytes, *, language: str = "zh") -> ASRResult:
        await asyncio.sleep(0.2)  # 模拟识别延时
        idx = len(audio) % len(_MOCK_PHRASES)
        text = _MOCK_PHRASES[idx]
        logger.info("Mock ASR 返回：{}", text)
        return ASRResult(text, language=language)

    async def stream_transcribe(
        self, audio: bytes, *, language: str = "zh"
    ) -> AsyncIterator[str]:
        await asyncio.sleep(0.15)
        idx = len(audio) % len(_MOCK_PHRASES)
        text = _MOCK_PHRASES[idx]
        # 按词流式输出，模拟实时识别
        for token in re.findall(r"[\u4e00-\u9fa5]+|[A-Za-z]+", text):
            await asyncio.sleep(0.08)
            yield token
        # 最后补一个空串标记结束
        yield ""


# ---- OpenAI Whisper 兼容适配器 ----
class OpenAIASRAdapter:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        self.api_key = api_key or settings.asr_api_key
        self.base_url = (base_url or settings.asr_base_url).rstrip("/")
        self.model = model or settings.asr_model

    async def transcribe(self, audio: bytes, *, language: str = "zh") -> ASRResult:
        text = await self._call_whisper(audio, language)
        return ASRResult(text, language=language)

    async def stream_transcribe(
        self, audio: bytes, *, language: str = "zh"
    ) -> AsyncIterator[str]:
        # Whisper 不原生支持流式，先整体识别再按词切分输出
        text = await self._call_whisper(audio, language)
        for token in re.findall(r"[\u4e00-\u9fa5]+|[A-Za-z]+", text):
            await asyncio.sleep(0.08)
            yield token
        yield ""

    async def _call_whisper(self, audio: bytes, language: str) -> str:
        files = {
            "file": ("audio.webm", audio, "audio/webm"),
            "model": (None, self.model),
            "language": (None, language),
            "response_format": (None, "json"),
        }
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{self.base_url}/audio/transcriptions",
                files=files,
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            if resp.status_code != 200:
                raise AdapterError(
                    ErrorCode.ADAPTER_ASR_FAILED,
                    f"ASR 请求失败：HTTP {resp.status_code}",
                    details={"body": resp.text[:512]},
                )
            data = resp.json()
            return data.get("text", "").strip()


# ---- Vosk 离线 ASR 适配器（无需 API Key，本地识别）----
class VoskASRAdapter:
    """使用 Vosk 进行离线中文语音识别。

    无需 API Key，无需联网，模型加载后本地识别。
    """

    _model = None  # 类级别单例，避免重复加载

    def __init__(self) -> None:
        from vosk import Model

        model_paths = [
            "models/vosk-model-small-cn-0.22",
            "backend/models/vosk-model-small-cn-0.22",
        ]
        import os

        model_path = None
        for p in model_paths:
            if os.path.isdir(p):
                model_path = p
                break

        if model_path is None:
            raise FileNotFoundError("Vosk 模型未找到，请先下载模型")

        if VoskASRAdapter._model is None:
            VoskASRAdapter._model = Model(model_path)
            logger.info("Vosk 模型已加载：{}", model_path)
        self.model = VoskASRAdapter._model

    async def transcribe(self, audio: bytes, *, language: str = "zh") -> ASRResult:
        import json
        import wave
        import tempfile
        import os
        from vosk import KaldiRecognizer

        # Vosk 需要 WAV 格式（16kHz, 16-bit, mono）
        # 先将上传的音频转换为 WAV
        wav_path = await self._to_wav(audio)

        try:
            wf = wave.open(wav_path, "rb")
            if wf.getnchannels() != 1:
                logger.warning("Vosk 需要单声道音频，正在自动转换")

            rec = KaldiRecognizer(self.model, wf.getframerate())
            rec.SetWords(True)

            results = []
            while True:
                data = wf.readframes(4000)
                if len(data) == 0:
                    break
                if rec.AcceptWaveform(data):
                    result = json.loads(rec.Result())
                    if result.get("text"):
                        results.append(result["text"])

            # 最后获取剩余结果
            final = json.loads(rec.FinalResult())
            if final.get("text"):
                results.append(final["text"])

            text = "".join(results).strip()
            # Vosk 中文识别结果含多余空格（如 "你好 你 是 谁"），去除中文间空格
            text = re.sub(r"([\u4e00-\u9fa5])\s+([\u4e00-\u9fa5])", r"\1\2", text)
            text = re.sub(r"([\u4e00-\u9fa5])\s+([\u4e00-\u9fa5])", r"\1\2", text)
            logger.info("Vosk ASR 返回：{}", text)
            return ASRResult(text, language=language)
        finally:
            try:
                os.remove(wav_path)
            except OSError:
                pass

    async def stream_transcribe(
        self, audio: bytes, *, language: str = "zh"
    ) -> AsyncIterator[str]:
        # Vosk 不支持真正的流式，先整体识别再按词输出
        result = await self.transcribe(audio, language=language)
        for token in re.findall(r"[\u4e00-\u9fa5]+|[A-Za-z]+", result.text):
            await asyncio.sleep(0.08)
            yield token
        yield ""

    async def _to_wav(self, audio: bytes) -> str:
        """将音频转换为 16kHz 16-bit mono WAV（Vosk 要求格式）。

        优先使用 PyAV（av 库），回退到 ffmpeg 命令行。
        """
        import tempfile
        import os
        import io

        tmp_out = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp_out.close()

        # 方式1：使用 PyAV 库转换（不依赖 PATH）
        try:
            import av
            import wave

            input_container = av.open(io.BytesIO(audio))
            output_container = av.open(tmp_out.name, mode="w", format="wav")

            output_stream = output_container.add_stream(
                "pcm_s16le",
                rate=16000,
                layout="mono",
            )

            for frame in input_container.decode(audio=0):
                # 重采样到 16kHz mono
                resampler = av.AudioResampler(
                    format="s16", layout="mono", rate=16000
                )
                resampled = resampler.resample(frame)
                for r in resampled:
                    output_container.mux(r)

            input_container.close()
            output_container.close()

            if os.path.getsize(tmp_out.name) > 0:
                return tmp_out.name
        except Exception as e:
            logger.warning("PyAV 转换失败，尝试 ffmpeg 命令行：{}", e)

        # 方式2：使用 ffmpeg 命令行
        try:
            import asyncio

            tmp_in = tempfile.NamedTemporaryFile(suffix=".webm", delete=False)
            tmp_in.write(audio)
            tmp_in.close()

            proc = await asyncio.create_subprocess_exec(
                "ffmpeg", "-y", "-i", tmp_in.name,
                "-ar", "16000", "-ac", "1", "-acodec", "pcm_s16le",
                tmp_out.name,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()
            os.remove(tmp_in.name)

            if os.path.exists(tmp_out.name) and os.path.getsize(tmp_out.name) > 0:
                return tmp_out.name
        except Exception as e:
            logger.warning("ffmpeg 命令行转换也失败：{}", e)

        # 方式3：直接写入原始数据（最后手段）
        with open(tmp_out.name, "wb") as f:
            f.write(audio)
        return tmp_out.name


# ---- faster-whisper 离线 ASR 适配器（基于 Whisper 架构，精度高）----
class WhisperASRAdapter:
    """使用 faster-whisper 进行离线中文语音识别。

    基于 OpenAI Whisper 架构，精度远超 Vosk 小模型。
    首次使用时自动下载模型（small 约 244MB），后续从缓存加载。
    无需 API Key，无需联网（首次下载除外）。
    """

    _model = None  # 类级别单例

    def __init__(self, model_size: str = "small") -> None:
        if WhisperASRAdapter._model is None:
            import os
            # 使用 HuggingFace 中国镜像，避免下载超时
            os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
            from faster_whisper import WhisperModel

            logger.info("正在加载 Whisper {} 模型（首次需下载，约 244MB）...", model_size)
            WhisperASRAdapter._model = WhisperModel(
                model_size,
                device="cpu",
                compute_type="int8",
            )
            logger.info("Whisper {} 模型已加载", model_size)
        self.model = WhisperASRAdapter._model

    async def transcribe(self, audio: bytes, *, language: str = "zh") -> ASRResult:
        import tempfile
        import os

        # 写入临时文件
        tmp_in = tempfile.NamedTemporaryFile(suffix=".webm", delete=False)
        tmp_in.write(audio)
        tmp_in.close()

        try:
            # faster-whisper 的 transcribe 是同步的，用线程池避免阻塞事件循环
            segments, _ = await asyncio.to_thread(
                self.model.transcribe,
                tmp_in.name,
                language="zh" if language.startswith("zh") else None,
                beam_size=5,
                vad_filter=True,
            )
            text = "".join(seg.text for seg in segments).strip()
            logger.info("Whisper ASR 返回：{}", text)
            return ASRResult(text, language=language)
        finally:
            try:
                os.remove(tmp_in.name)
            except OSError:
                pass

    async def stream_transcribe(
        self, audio: bytes, *, language: str = "zh"
    ) -> AsyncIterator[str]:
        # Whisper 不支持真正的流式，先整体识别再按词输出
        result = await self.transcribe(audio, language=language)
        for token in re.findall(r"[\u4e00-\u9fa5]+|[A-Za-z]+", result.text):
            await asyncio.sleep(0.08)
            yield token
        yield ""


_asr_adapter: ASRAdapter | None = None
_asr_adapter_name: str = ""  # 当前实际使用的 ASR 适配器名称（前端用于显示精度来源）
_volc_status: str = "unknown"  # unknown / ok / bad (403 资源未开通)


def get_asr_adapter_name() -> str:
    """返回当前实际 ASR 适配器的可读名称（如"豆包ASR"、"Whisper离线"、"Vosk离线"等）。"""
    return _asr_adapter_name


# ---- 豆包大模型极速版 HTTP ASR 适配器（火山引擎语音服务）----
class VolcFlashASRAdapter(ASRAdapter):
    """火山引擎「大模型录音文件识别极速版」HTTP 适配器。

    控制台需开通：https://console.volcengine.com/speech/service/10035
    资源 ID 默认为 volc.bigasr.auc_turbo；失败时自动降级到离线识别。
    """

    _ENDPOINT = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/recognize/flash"
    _TIMEOUT = 120.0

    def __init__(self) -> None:
        if not settings.volc_asr_app_key:
            raise AdapterError(ErrorCode.ADAPTER_ASR_FAILED, "VOLC_ASR_X_API_KEY not set")
        self._api_key = settings.volc_asr_app_key
        self._resource_id = settings.volc_asr_resource_id or "volc.bigasr.auc_turbo"
        self._client = httpx.AsyncClient(timeout=self._TIMEOUT)

    async def transcribe(self, audio_bytes, *, language="zh", sample_rate=None):
        b64 = base64.b64encode(audio_bytes).decode("ascii")
        uid = self._api_key[:16]
        head = audio_bytes[:8] if len(audio_bytes) >= 8 else b""
        if head.startswith(b"RIFF"):
            fmt, codec = "wav", "raw"
        elif head[:4] == b"OggS":
            fmt, codec = "ogg", "opus"
        else:
            fmt, codec = "ogg", "opus"
        payload = {
            "user": {"uid": uid},
            "audio": {
                "data": b64,
                "format": fmt,
                "codec": codec,
                "rate": sample_rate or 16000,
                "bits": 16,
                "channel": 1,
            },
            "request": {
                "model_name": "bigmodel",
                "enable_itn": True,
                "enable_punc": True,
                "enable_ddc": False,
            },
        }
        headers = {
            "X-Api-Key": self._api_key,
            "X-Api-Resource-Id": self._resource_id,
            "X-Api-Request-Id": str(_uuid.uuid4()),
            "X-Api-Sequence": "-1",
        }
        try:
            resp = await self._client.post(self._ENDPOINT, json=payload, headers=headers)
        except Exception as exc:
            msg = str(exc).lower()
            if "timeout" in msg or "401" in msg or "403" in msg or "auth" in msg:
                VolcFlashASRAdapter._mark_volc_unavailable()
            raise AdapterError(ErrorCode.ADAPTER_ASR_FAILED, f"ASR network failed") from exc
        if resp.status_code != 200:
            if resp.status_code in (401, 403):
                VolcFlashASRAdapter._mark_volc_unavailable()
            raise AdapterError(
                ErrorCode.ADAPTER_ASR_FAILED,
                f"ASR HTTP {resp.status_code}: {resp.text[:200]}",
            )
        data = resp.json()
        code = data.get("code") or data.get("StatusCode") or 0
        if code and str(code) not in ("0", "20000000"):
            m = data.get("message") or data.get("StatusMessage") or ""
            if str(code) == "45000030" or "not granted" in m or "resource" in m.lower():
                VolcFlashASRAdapter._mark_volc_unavailable()
            raise AdapterError(
                ErrorCode.ADAPTER_ASR_FAILED, f"ASR err code={code} msg={m}"
            )
        text = ""
        global _volc_status
        try:
            text = data["result"]["text"].strip()
        except Exception:
            utts = (data.get("result") or {}).get("utterances") or []
            if utts:
                text = utts[0].get("text", "").strip()
        import re as _re

        text = _re.sub(r"([\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", r"\1", text)
        _volc_status = "ok"
        logger.info("豆包ASR返回：{}", text)
        return ASRResult(text or "", language=language or "zh", confidence=0.95)

    @staticmethod
    def _mark_volc_unavailable() -> None:
        """标记豆包 ASR 不可用并清空缓存，下次请求自动走离线 Whisper/Vosk。"""
        global _volc_status, _asr_adapter
        if _volc_status == "bad":
            return
        _volc_status = "bad"
        _asr_adapter = None
        logger.warning("豆包 ASR 资源未开通或鉴权失败，已自动降级到离线识别")

    async def stream_transcribe(self, audio: bytes, *, language: str = "zh"):
        # 豆包 HTTP 极速版不支持原生流式，先整体识别再切片输出（模拟流式）
        result = await self.transcribe(audio, language=language)
        import re as _re_mod

        tokens = _re_mod.findall(r"[\u4e00-\u9fff]+|[A-Za-z0-9]+|[，。、！？]", result.text)
        if not tokens and result.text:
            tokens = [result.text]
        for tk in tokens:
            yield tk
        yield ""


def get_asr_adapter() -> ASRAdapter:
    """根据配置返回适配器（缓存单例，避免重复初始化）。

    优先级：豆包大模型ASR > OpenAI API > Whisper（高精度离线） > Vosk（兜底） > Mock
    （Whisper 首次需下载 small 模型约 244MB，国内环境可用）
    """
    global _asr_adapter, _asr_adapter_name, _volc_status
    if _asr_adapter is not None:
        return _asr_adapter

    # 1. 豆包大模型极速版 HTTP ASR（配置 VOLC_ASR_X_API_KEY 即启用，_volc_status=bad 时自动跳过）
    if settings.volc_asr_app_key and _volc_status != "bad":
        try:
            _asr_adapter = VolcFlashASRAdapter()
            _asr_adapter_name = "豆包大模型"
            logger.info("使用 豆包大模型极速版 HTTP ASR 适配器")
            return _asr_adapter
        except Exception as e:  # noqa: BLE001
            logger.warning("豆包ASR初始化失败：{}", e)
            _volc_status = "bad"

    # 2. OpenAI Whisper 兼容 API
    if settings.asr_api_key:
        try:
            _asr_adapter = OpenAIASRAdapter()
            _asr_adapter_name = "OpenAI Whisper"
            logger.info("使用 OpenAI ASR 适配器")
            return _asr_adapter
        except Exception as e:  # noqa: BLE001
            logger.warning("ASR 适配器初始化失败：{}", e)

    # 3. faster-whisper 离线识别（Whisper 架构，精度远超 Vosk 小模型）
    try:
        _asr_adapter = WhisperASRAdapter()
        _asr_adapter_name = "Whisper 离线"
        logger.info("使用 Whisper 离线 ASR 适配器（高精度）")
        return _asr_adapter
    except Exception as e:  # noqa: BLE001
        logger.warning("Whisper 不可用：{}", e)

    # 4. Vosk 离线识别（40MB 中文小模型，国内可用，精度较低 — 仅作兜底）
    try:
        _asr_adapter = VoskASRAdapter()
        _asr_adapter_name = "Vosk 离线"
        logger.info("使用 Vosk 离线 ASR 适配器（兜底）")
        return _asr_adapter
    except Exception as e:  # noqa: BLE001
        logger.warning("Vosk 不可用：{}", e)

    # 5. 最后回退到 Mock
    _asr_adapter = MockASRAdapter()
    _asr_adapter_name = "演示模式(Mock)"
    return _asr_adapter
