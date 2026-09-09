"""MCP 工具层：注册、参数校验、超时与错误处理。"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable
from typing import Any, Protocol, get_args, get_origin, get_type_hints

from app.core.errors import ErrorCode, ToolError
from app.core.logging import get_logger

logger = get_logger()

_DEFAULT_TIMEOUT = 8.0

# 允许被调用的工具白名单（按名称）。
# 新增工具时必须显式登记，避免「注册即对模型可用」导致越权调用。
_ALLOWED_TOOLS: set[str] = {
    "service_query",
    "route_query",
    "map_query",
    "translate",
}

# 支持的参数类型（用于运行前校验）
_SIMPLE_TYPES: dict[Any, tuple[type, ...]] = {
    str: (str,),
    int: (int,),
    float: (int, float),
    bool: (bool,),
}


class Tool(Protocol):
    """工具协议。

    `run` 声明为 `Callable[..., Any]` 而不是 `async def run(self, **args)`：
    各工具都有自己明确的参数签名，注册表通过 `inspect.signature` 反射校验后再调用，
    用 `**args` 反而会让类型检查器判定所有实现都不符合协议。
    """

    name: str
    description: str
    run: Callable[..., Any]


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool
        logger.info("已注册工具：{}", tool.name)

    def list_tools(self) -> list[dict]:
        return [
            {"name": t.name, "description": t.description}
            for t in self._tools.values()
            if t.name in _ALLOWED_TOOLS
        ]

    async def call(self, name: str, args: dict[str, Any], *, timeout: float = _DEFAULT_TIMEOUT) -> dict:
        if name not in _ALLOWED_TOOLS:
            raise ToolError(ErrorCode.TOOL_NOT_FOUND, f"工具不在白名单中：{name}")
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
    params = {name: p for name, p in sig.parameters.items() if name != "self"}
    # 注意：tools.py 使用了 `from __future__ import annotations`，
    # signature 里的注解是字符串，必须解析成真实类型才能做 isinstance 校验。
    try:
        hints = get_type_hints(tool.run)
    except Exception:  # noqa: BLE001
        hints = {}

    # 1. 拒绝未知参数：静默丢弃会把「参数名写错」伪装成正常调用
    unknown = [k for k in args if k not in params]
    if unknown:
        raise ToolError(
            ErrorCode.TOOL_PARAM_INVALID,
            f"未知参数：{unknown}",
            details={"tool": tool.name, "allowed": sorted(params)},
        )

    # 2. 必填参数检查
    missing = [
        name
        for name, param in params.items()
        if param.default is inspect.Parameter.empty and name not in args
    ]
    if missing:
        raise ToolError(ErrorCode.TOOL_PARAM_INVALID, f"缺少参数：{missing}", details={"tool": tool.name})

    # 3. 类型校验（只校验基础类型；复杂类型交给工具自身处理）
    for key, value in args.items():
        annotation = hints.get(key, params[key].annotation)
        if annotation is inspect.Parameter.empty or value is None:
            continue
        origin = get_origin(annotation)
        if origin is not None:  # Optional[X] / list[X] 等，取第一个非 None 参数
            candidates = [a for a in get_args(annotation) if a is not type(None)]
            annotation = candidates[0] if candidates else None
        expected = _SIMPLE_TYPES.get(annotation)
        if expected and not isinstance(value, expected):
            raise ToolError(
                ErrorCode.TOOL_PARAM_INVALID,
                f"参数类型错误：{key} 期望 {getattr(annotation, '__name__', annotation)}",
                details={"tool": tool.name},
            )

    return await tool.run(**args)


# 单例
registry = ToolRegistry()
