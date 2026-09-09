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

import asyncio
import base64
import re
import time
import uuid as _uuid
from collections.abc import AsyncIterator
from typing import Any, Protocol

import httpx

from app.core.config import settings
from app.core.errors import AdapterError, ErrorCode
from app.core.http import get_http_client
from app.core.logging import get_logger

logger = get_logger()


class ASRResult:
    """ASR 转写结果。"""

    def __init__(self, text: str, *, language: str = "zh", confidence: float = 1.0) -> None:
        self.text = text
        self.language = language
        self.confidence = confidence


class ASRAdapter(Protocol):
    """ASR 统一接口。

    `stream_transcribe` 是异步生成器（不是 `async def -> AsyncIterator`），
    否则类型检查器会认为它返回协程，无法校验适配器是否符合协议。
    """

    async def transcribe(self, audio: bytes, *, language: str = "zh") -> ASRResult: ...

    def stream_transcribe(self, audio: bytes, *, language: str = "zh") -> AsyncIterator[str]: ...


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
        # 按词分块输出（不逐词 sleep，避免人为拖慢字幕）
        for token in re.findall(r"[\u4e00-\u9fa5]+|[A-Za-z]+", text):
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
        # Whisper 不原生支持流式，先整体识别再按词切分输出（不逐词 sleep）
        text = await self._call_whisper(audio, language)
        for token in re.findall(r"[\u4e00-\u9fa5]+|[A-Za-z]+", text):
            yield token
        yield ""

    async def _call_whisper(self, audio: bytes, language: str) -> str:
        files: dict[str, Any] = {
            "file": ("audio.webm", audio, "audio/webm"),
            "model": (None, self.model),
            "language": (None, language),
            "response_format": (None, "json"),
        }
        # 复用进程级共享连接池（原实现每次调用新建 AsyncClient，握手开销 + 句柄泄漏）
        client = get_http_client()
        resp = await client.post(
            f"{self.base_url}/audio/transcriptions",
            files=files,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=60.0,
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

        # 单事件循环内同步初始化（无 await 点）天然原子，不会并发加载两份模型
        if VoskASRAdapter._model is None:
            VoskASRAdapter._model = Model(model_path)
            logger.info("Vosk 模型已加载：{}", model_path)
        self.model = VoskASRAdapter._model
    async def transcribe(self, audio: bytes, *, language: str = "zh") -> ASRResult:
        import os

        # Vosk 需要 WAV 格式（16kHz, 16-bit, mono）
        # 先将上传的音频转换为 WAV
        wav_path = await self._to_wav(audio)

        try:
            # Kaldi 识别为同步 CPU 密集操作，整体放入线程池，避免阻塞事件循环
            text = await asyncio.to_thread(self._recognize_wav, wav_path)
            logger.info("Vosk ASR 返回：{}", text)
            return ASRResult(text, language=language)
        finally:
            try:
                os.remove(wav_path)
            except OSError:
                pass

    def _recognize_wav(self, wav_path: str) -> str:
        """同步 WAV 识别（在线程池中执行）。"""
        import json
        import wave

        from vosk import KaldiRecognizer

        with wave.open(wav_path, "rb") as wf:  # with 确保关闭，Windows 上才能删除临时文件
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

            final = json.loads(rec.FinalResult())
            if final.get("text"):
                results.append(final["text"])

        text = "".join(results).strip()
        # Vosk 中文识别结果含多余空格（如 "你好 你 是 谁"）；lookahead 单次遍历即可处理连续空格
        return re.sub(r"([\u4e00-\u9fa5])\s+(?=[\u4e00-\u9fa5])", r"\1", text)

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
        解码/重采样为同步 CPU 密集操作，放入线程池避免阻塞事件循环。
        """
        import os
        import tempfile

        tmp_out = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp_out.close()

        # 方式1：使用 PyAV 库转换（不依赖 PATH）
        try:
            await asyncio.to_thread(self._convert_with_pyav, audio, tmp_out.name)
            if os.path.getsize(tmp_out.name) > 0:
                return tmp_out.name
        except Exception as e:
            logger.warning("PyAV 转换失败，尝试 ffmpeg 命令行：{}", e)

        # 方式2：使用 ffmpeg 命令行
        tmp_in = tempfile.NamedTemporaryFile(suffix=".webm", delete=False)
        try:
            tmp_in.write(audio)
        finally:
            tmp_in.close()
        try:
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg", "-y", "-i", tmp_in.name,
                "-ar", "16000", "-ac", "1", "-acodec", "pcm_s16le",
                tmp_out.name,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()

            if proc.returncode == 0 and os.path.exists(tmp_out.name) and os.path.getsize(tmp_out.name) > 0:
                return tmp_out.name
        except Exception as e:
            logger.warning("ffmpeg 命令行转换也失败：{}", e)
        finally:
            # 必须放在 finally：ffmpeg 不存在时 create_subprocess_exec 会抛异常，
            # 旧实现在正常路径才删除临时文件，异常时每次请求都会泄漏一个 .webm
            try:
                os.remove(tmp_in.name)
            except OSError:
                pass

        # 方式3：原始数据即 WAV 时直接使用；否则报错（避免 wave.open 解析非 WAV 抛裸异常）
        if audio[:4] == b"RIFF":
            with open(tmp_out.name, "wb") as f:
                f.write(audio)
            return tmp_out.name
        try:
            os.remove(tmp_out.name)
        except OSError:
            pass
        raise AdapterError(
            ErrorCode.ADAPTER_ASR_FAILED,
            "音频转换为 WAV 失败（未安装 ffmpeg 且音频格式不受支持）",
        )

    @staticmethod
    def _convert_with_pyav(audio: bytes, out_path: str) -> None:
        """PyAV 解码 + 重采样到 16kHz mono s16（在线程池中执行）。

        注意：`OutputContainer.mux()` 接受的是 **Packet**，不是 Frame。
        旧实现直接 `mux(frame)`，PyAV 内部会对参数做 `for packet in packets`
        迭代，于是抛 `TypeError: AudioFrame object is not iterable`——
        这条「首选」转换路径其实从未成功过，一直悄悄退到 ffmpeg 命令行。
        """
        import io

        import av

        input_container = av.open(io.BytesIO(audio))
        output_container = av.open(out_path, mode="w", format="wav")
        try:
            # av.open(BytesIO) 一定是输入容器；stub 里返回联合类型，这里显式收窄
            input_stream: Any = input_container
            output_stream = output_container.add_stream(
                "pcm_s16le",
                rate=16000,
                layout="mono",
            )
            resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
            for frame in input_stream.decode(audio=0):
                for resampled in resampler.resample(frame):
                    for packet in output_stream.encode(resampled):
                        output_container.mux(packet)
            # flush 编码器，否则末尾音频会丢失
            for packet in output_stream.encode(None):
                output_container.mux(packet)
        finally:
            input_container.close()
            output_container.close()


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
        import os
        import tempfile

        # 临时文件写入放入线程池（大音频同步写盘会阻塞事件循环）
        tmp_in = tempfile.NamedTemporaryFile(suffix=".webm", delete=False)
        try:
            await asyncio.to_thread(tmp_in.write, audio)
        finally:
            tmp_in.close()

        try:
            # transcribe 返回懒生成器：真正的 beam-search 解码发生在迭代 segments 时，
            # 因此把「调用 + 迭代拼文本」整体放入线程池，否则识别期间全站请求冻结
            def _run() -> str:
                segments, _ = self.model.transcribe(
                    tmp_in.name,
                    language="zh" if language.startswith("zh") else None,
                    beam_size=5,
                    vad_filter=True,
                )
                return "".join(seg.text for seg in segments).strip()

            text = await asyncio.to_thread(_run)
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

# 火山 ASR 降级状态机：冷却而非永久禁用
# _volc_cooldown_until 之前的时间戳内跳过云端 ASR；到期后自动重试恢复，
# 避免一次网络抖动导致整进程永久降级到离线识别。
_TRANSIENT_COOLDOWN_S = 120.0  # 网络超时/临时错误：冷却 2 分钟
_AUTH_COOLDOWN_S = 3600.0  # 鉴权失败/资源未开通：冷却 1 小时
_volc_cooldown_until: float = 0.0


def _volc_in_cooldown() -> bool:
    return time.monotonic() < _volc_cooldown_until


def get_asr_adapter_name() -> str:
    """返回当前实际 ASR 适配器的可读名称（如"豆包ASR"、"Whisper离线"、"Vosk离线"等）。"""
    return _asr_adapter_name


# ---- 豆包大模型极速版 HTTP ASR 适配器（火山引擎语音服务）----
class VolcFlashASRAdapter(ASRAdapter):
    """火山引擎「大模型录音文件识别极速版」HTTP 适配器。

    控制台需开通：https://console.volcengine.com/speech/service/10035
    资源 ID 默认为 volc.bigasr.auc_turbo；失败时按错误类型冷却降级到离线识别。
    """

    _ENDPOINT = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/recognize/flash"
    _TIMEOUT = 120.0

    def __init__(self) -> None:
        if not settings.volc_asr_app_key:
            raise AdapterError(ErrorCode.ADAPTER_ASR_FAILED, "VOLC_ASR_X_API_KEY not set")
        self._api_key = settings.volc_asr_app_key
        self._resource_id = settings.volc_asr_resource_id or "volc.bigasr.auc_turbo"

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
            resp = await get_http_client().post(
                self._ENDPOINT, json=payload, headers=headers, timeout=self._TIMEOUT
            )
        except httpx.TimeoutException as exc:
            # 网络超时属临时故障：短暂冷却后自动恢复
            _mark_volc_cooldown(_TRANSIENT_COOLDOWN_S)
            raise AdapterError(ErrorCode.ADAPTER_ASR_FAILED, "ASR network timeout") from exc
        except httpx.HTTPError as exc:
            _mark_volc_cooldown(_TRANSIENT_COOLDOWN_S)
            raise AdapterError(
                ErrorCode.ADAPTER_ASR_FAILED, f"ASR network failed: {type(exc).__name__}"
            ) from exc
        if resp.status_code != 200:
            if resp.status_code in (401, 403):
                _mark_volc_cooldown(_AUTH_COOLDOWN_S)
            raise AdapterError(
                ErrorCode.ADAPTER_ASR_FAILED,
                f"ASR HTTP {resp.status_code}: {resp.text[:200]}",
            )
        data = resp.json()
        code = data.get("code") or data.get("StatusCode") or 0
        if code and str(code) not in ("0", "20000000"):
            m = data.get("message") or data.get("StatusMessage") or ""
            if str(code) == "45000030" or "not granted" in m or "resource" in m.lower():
                _mark_volc_cooldown(_AUTH_COOLDOWN_S)
            raise AdapterError(
                ErrorCode.ADAPTER_ASR_FAILED, f"ASR err code={code} msg={m}"
            )
        text = ""
        try:
            text = data["result"]["text"].strip()
        except (KeyError, TypeError, AttributeError):
            utts = (data.get("result") or {}).get("utterances") or []
            if utts:
                text = utts[0].get("text", "").strip()
        if not text:
            logger.warning("豆包ASR返回空文本，响应字段可能变更，请检查上游协议")

        text = re.sub(r"([\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", r"\1", text)
        _clear_volc_cooldown()
        logger.info("豆包ASR返回：{}", text)
        return ASRResult(text or "", language=language or "zh", confidence=0.95)

    async def stream_transcribe(self, audio: bytes, *, language: str = "zh"):
        # 豆包 HTTP 极速版不支持原生流式，先整体识别再切片输出（模拟流式）
        result = await self.transcribe(audio, language=language)

        tokens = re.findall(r"[\u4e00-\u9fff]+|[A-Za-z0-9]+|[，。、！？]", result.text)
        if not tokens and result.text:
            tokens = [result.text]
        for tk in tokens:
            yield tk
        yield ""


def _mark_volc_cooldown(seconds: float) -> None:
    """标记豆包 ASR 进入冷却期并清空适配器缓存，下次请求自动走离线识别。"""
    global _asr_adapter, _volc_cooldown_until
    _volc_cooldown_until = max(_volc_cooldown_until, time.monotonic() + seconds)
    _asr_adapter = None
    logger.warning("豆包 ASR 不可用，冷却 {:.0f}s 后自动重试（期间使用离线识别）", seconds)


def _clear_volc_cooldown() -> None:
    global _volc_cooldown_until
    _volc_cooldown_until = 0.0


def get_asr_adapter() -> ASRAdapter:
    """根据配置返回适配器（缓存单例，避免重复初始化）。

    优先级：豆包大模型ASR > OpenAI API > Whisper（高精度离线） > Vosk（兜底） > Mock
    （Whisper 首次需下载 small 模型约 244MB，国内环境可用）
    """
    global _asr_adapter, _asr_adapter_name
    if _asr_adapter is not None:
        return _asr_adapter

    # 1. 豆包大模型极速版 HTTP ASR（配置 VOLC_ASR_X_API_KEY 即启用；
    #    处于冷却期时自动跳过，冷却到期后自动恢复重试）
    if settings.volc_asr_app_key and not _volc_in_cooldown():
        try:
            _asr_adapter = VolcFlashASRAdapter()
            _asr_adapter_name = "豆包大模型"
            logger.info("使用 豆包大模型极速版 HTTP ASR 适配器")
            return _asr_adapter
        except Exception as e:  # noqa: BLE001
            logger.warning("豆包ASR初始化失败：{}", e)
            _mark_volc_cooldown(_AUTH_COOLDOWN_S)

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
