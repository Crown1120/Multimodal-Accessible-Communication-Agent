"""MCP 工具层：注册、参数校验、超时与错误处理。"""

from __future__ import annotations

import asyncio
import inspect
from typing import Any, Protocol

from app.core.errors import ErrorCode, ToolError
from app.core.logging import get_logger

logger = get_logger()

_DEFAULT_TIMEOUT = 8.0


class Tool(Protocol):
    name: str
    description: str

    async def run(self, **args: Any) -> dict: ...


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool
        logger.info("已注册工具：{}", tool.name)

    def list_tools(self) -> list[dict]:
        return [{"name": t.name, "description": t.description} for t in self._tools.values()]

    async def call(self, name: str, args: dict[str, Any], *, timeout: float = _DEFAULT_TIMEOUT) -> dict:
        tool = self._tools.get(name)
        if tool is None:
            raise ToolError(ErrorCode.TOOL_NOT_FOUND, f"工具不存在：{name}")
        try:
            result = await asyncio.wait_for(_call_tool(tool, args), timeout=timeout)
            return result
        except TimeoutError as e:
            raise ToolError(ErrorCode.TOOL_TIMEOUT, f"工具超时：{name}", details={"timeout": timeout}) from e
        except ToolError:
            raise
        except Exception as e:  # noqa: BLE001
            logger.exception("工具调用失败：{}", name)
            raise ToolError(ErrorCode.TOOL_FAILED, f"工具执行失败：{name}", details={"reason": str(e)}) from e


async def _call_tool(tool: Tool, args: dict[str, Any]) -> dict:
    sig = inspect.signature(tool.run)
    valid = {k: v for k, v in args.items() if k in sig.parameters}
    missing = [p for p, v in sig.parameters.items() if v.default is inspect._empty and p not in valid]
    if missing:
        raise ToolError(ErrorCode.TOOL_PARAM_INVALID, f"缺少参数：{missing}", details={"tool": tool.name})
    return await tool.run(**valid)


# 单例
registry = ToolRegistry()
