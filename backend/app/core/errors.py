"""错误码与统一异常定义。

错误码命名约定：<模块缩写>_<4位编号>
- 1xxx: 通用 / 鉴权
- 2xxx: 会话与消息
- 3xxx: Agent 编排
- 4xxx: RAG 检索
- 5xxx: MCP 工具
- 6xxx: 适配器（LLM/ASR/TTS/数字人）
"""

from __future__ import annotations

from enum import Enum


class ErrorCode(str, Enum):
    """统一错误码。"""

    # 通用
    INTERNAL_ERROR = "ERR_1000"
    BAD_REQUEST = "ERR_1001"
    NOT_FOUND = "ERR_1002"
    VALIDATION_ERROR = "ERR_1003"
    UNAUTHORIZED = "ERR_1004"

    # 会话与消息
    SESSION_NOT_FOUND = "ERR_2001"
    SESSION_CLOSED = "ERR_2002"
    MESSAGE_EMPTY = "ERR_2003"

    # Agent
    AGENT_UNEXPECTED = "ERR_3001"
    AGENT_TIMEOUT = "ERR_3002"
    AGENT_LOW_CONFIDENCE = "ERR_3003"

    # RAG
    RAG_NO_RESULT = "ERR_4001"
    RAG_LOW_CONFIDENCE = "ERR_4002"
    RAG_INDEX_FAILED = "ERR_4003"

    # MCP 工具
    TOOL_NOT_FOUND = "ERR_5001"
    TOOL_PARAM_INVALID = "ERR_5002"
    TOOL_TIMEOUT = "ERR_5003"
    TOOL_FAILED = "ERR_5004"

    # 适配器
    ADAPTER_LLM_FAILED = "ERR_6001"
    ADAPTER_ASR_FAILED = "ERR_6002"
    ADAPTER_TTS_FAILED = "ERR_6003"
    ADAPTER_DH_FAILED = "ERR_6004"


class BridgeError(Exception):
    """业务异常基类。"""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        details: dict | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(message)


# 便捷子类
class SessionError(BridgeError):
    """会话相关异常。"""


class AgentError(BridgeError):
    """Agent 编排异常。"""


class ToolError(BridgeError):
    """工具调用异常。"""


class AdapterError(BridgeError):
    """外部服务适配器异常（LLM/ASR/TTS/数字人）。"""
