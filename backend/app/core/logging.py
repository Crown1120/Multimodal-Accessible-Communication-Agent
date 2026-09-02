"""日志配置。

基于 loguru，统一 JSON 格式，支持文件轮转和脱敏。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from loguru import logger

from app.core.config import settings

# 需要脱敏的字段名模式
_SENSITIVE_KEYS = re.compile(r"(token|secret|password|api_key|apikey)", re.IGNORECASE)


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

    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}:{function}:{line}</cyan> - <level>{message}</level>"
    )

    # 控制台
    logger.add(
        sys.stdout,
        level=settings.log_level,
        format=log_format,
        colorize=True,
        backtrace=settings.debug,
        diagnose=settings.debug,
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

    logger.info("日志系统已就绪，级别={}，文件={}", settings.log_level, settings.log_file)


def get_logger():
    """获取已配置的 logger。"""
    return logger
