"""应用配置。

从环境变量加载配置，提供默认值。配置覆盖顺序：
环境变量 > .env 文件 > 默认值。
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Bridge 应用配置。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # 应用
    app_name: str = "Bridge"
    app_version: str = "0.1.0"
    environment: str = Field(default="development", description="运行环境：development/staging/production")
    debug: bool = Field(default=True, description="调试模式")
    api_prefix: str = "/api"

    # 服务
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"],
        description="允许跨域的前端来源",
    )

    # 数据库
    sqlite_url: str = "sqlite+aiosqlite:///./bridge.db"
    sqlite_echo: bool = False

    # 向量库
    chroma_path: str = "./chroma_data"
    chroma_collection: str = "bridge_knowledge"

    # LLM（占位，后续接入适配器）
    llm_provider: str = "openai"
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"

    # ASR（语音转文字，阶段3接入）
    asr_provider: str = "openai"
    asr_api_key: str = ""
    asr_base_url: str = "https://api.openai.com/v1"
    asr_model: str = "whisper-1"
    asr_language: str = "zh"

    # TTS（文字转语音，阶段3接入，支持慢速）
    tts_provider: str = "openai"
    tts_api_key: str = ""
    tts_base_url: str = "https://api.openai.com/v1"
    tts_model: str = "tts-1"
    tts_voice: str = "alloy"
    tts_speed: float = Field(default=1.0, description="语音语速 0.5-2.0，老年模式建议 0.8")

    # 会话
    session_timeout_minutes: int = 60
    # 日志
    log_level: str = "INFO"
    log_file: str = "./logs/bridge.log"


@lru_cache
def get_settings() -> Settings:
    """获取单例配置。"""
    return Settings()


settings = get_settings()
