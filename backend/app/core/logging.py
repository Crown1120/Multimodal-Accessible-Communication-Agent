"""日志配置。

基于 loguru，统一 JSON 格式，支持文件轮转和脱敏。
"""

from __future__ import annotations

import re
import sys
from contextvars import ContextVar
from pathlib import Path

from loguru import logger

from app.core.config import settings

# 需要脱敏的字段名模式
_SENSITIVE_KEYS = re.compile(r"(token|secret|password|api_key|apikey)", re.IGNORECASE)

# 请求ID上下文（用于链路追踪，中间件设置）
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


def _inject_extra(record) -> None:
    """把请求 ID 等上下文写入 record["extra"]。

    注意：loguru 的 `format=` 若传函数，其返回值会被当作**格式模板**再做一次
    `format_map`，因此原来「返回 JSON 字符串」的写法会在每条日志上抛
    `KeyError: '"ts"'`。结构化日志应改用 `serialize=True` + patcher。
    """
    record["extra"]["request_id"] = request_id_var.get()


def _redact_message(message: str) -> str:
    """对日志消息中明显的敏感字段进行脱敏。"""

    def _red(match: re.Match[str]) -> str:
        key = match.group(1)
        sep = match.group(2)
        return f"{key}{sep}***"

    # 匹配 key=value 或 key: value（含可选引号），不破坏整体结构
    pattern = re.compile(
        r'(?i)(\w*(?:token|secret|password|api_?key)\w*)(\s*[:=]\s*)"?[^\s,"]+'
    )
    return pattern.sub(_red, message)


def _redact_filter(record) -> bool:
    """日志过滤器：对敏感信息脱敏后保留记录。任何异常都不阻断日志。"""
    try:
        message = record["message"]
        redacted = _redact_message(message)
        record["message"] = redacted
    except Exception:  # noqa: BLE001
        pass
    return True


def setup_logging() -> None:
    """初始化全局日志。"""
    logger.remove()
    # 把请求 ID 注入每条日志的 extra，供 JSON 结构化日志使用
    logger.configure(patcher=_inject_extra)

    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}:{function}:{line}</cyan> - <level>{message}</level>"
    )

    # 控制台（同样需要脱敏：容器日志同样会外泄密钥）
    logger.add(
        sys.stdout,
        level=settings.log_level,
        format=log_format,
        colorize=True,
        backtrace=settings.debug,
        diagnose=settings.debug,
        filter=_redact_filter,
    )

    # 文件（轮转 + 保留）
    log_path = Path(settings.log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger.add(
        str(log_path),
        level=settings.log_level,
        rotation="10 MB",
        retention="14 days",
        compression="zip",
        format=(
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
            "{name}:{function}:{line} - {message}"
        ),
        backtrace=settings.debug,
        diagnose=settings.debug,
        filter=_redact_filter,
    )

    # JSON 结构化文件（生产环境，便于日志采集）
    # 用 loguru 内建 serialize=True（原来把 JSON 字符串当 format 模板会抛 KeyError）
    json_log_path = log_path.with_suffix(".jsonl")
    logger.add(
        str(json_log_path),
        level=settings.log_level,
        rotation="10 MB",
        retention="14 days",
        compression="zip",
        serialize=True,
        filter=_redact_filter,
    )

    logger.info("日志系统已就绪，级别={}，文件={}", settings.log_level, settings.log_file)


def get_logger():
    """获取已配置的 logger。"""
    return logger
