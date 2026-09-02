"""ASR（语音转文字）适配器。

- ASRAdapter：统一接口（整体转写 + 流式增量转写）
- MockASRAdapter：规则式转写，便于无 API Key 时演示核心闭环
- OpenAIASRAdapter：兼容 OpenAI Whisper API

外部服务不可用时降级到 Mock，保证闭环可演示。
"""

from __future__ import annotations

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


def get_asr_adapter() -> ASRAdapter:
    """根据配置返回适配器（缓存单例，避免重复初始化）。

    优先级：OpenAI API > Vosk > Whisper > Mock
    （Whisper 需从 HuggingFace 下载，国内可能不可用）
    """
    global _asr_adapter
    if _asr_adapter is not None:
        return _asr_adapter

    # 1. 优先使用 OpenAI API（如果配置了 Key）
    if settings.asr_api_key:
        try:
            _asr_adapter = OpenAIASRAdapter()
            logger.info("使用 OpenAI ASR 适配器")
            return _asr_adapter
        except Exception as e:  # noqa: BLE001
            logger.warning("ASR 适配器初始化失败：{}", e)

    # 2. 优先使用 Vosk 离线识别（国内可用，无需联网）
    try:
        _asr_adapter = VoskASRAdapter()
        logger.info("使用 Vosk 离线 ASR 适配器")
        return _asr_adapter
    except Exception as e:  # noqa: BLE001
        logger.warning("Vosk 不可用：{}", e)

    # 3. 尝试 faster-whisper（需从 HuggingFace 下载，国内可能不可用）
    try:
        _asr_adapter = WhisperASRAdapter()
        logger.info("使用 Whisper ASR 适配器")
        return _asr_adapter
    except Exception as e:  # noqa: BLE001
        logger.warning("Whisper 不可用：{}", e)

    # 4. 最后回退到 Mock
    _asr_adapter = MockASRAdapter()
    return _asr_adapter
