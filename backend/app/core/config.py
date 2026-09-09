"""应用配置。

从环境变量加载配置，提供默认值。配置覆盖顺序：
环境变量 > .env 文件 > 默认值。
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, model_validator
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
    # PostgreSQL（可选，设置后优先使用；格式：postgresql+asyncpg://user:pass@host:5432/dbname）
    postgres_url: str = Field(default="", description="PostgreSQL 连接串，为空时使用 SQLite")
    auto_migrate: bool = Field(
        default=True,
        description="启动时执行 Alembic 迁移（upgrade head）；关闭则退化为 create_all",
    )

    # 向量库
    chroma_path: str = "./chroma_data"
    chroma_collection: str = "bridge_knowledge"
    # 是否启用 Chroma 向量库（本项目默认使用内存中文 n-gram 检索，置空即为禁用）
    chroma_embedding: str = ""

    # LLM（占位，后续接入适配器）
    llm_provider: str = "openai"
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    llm_max_tokens: int = Field(default=512, description="单次回复最大 token 数，0 表示不限制")
    llm_temperature: float | None = Field(default=0.3, description="采样温度，None 表示不传该参数")
    llm_max_retries: int = Field(default=2, description="LLM 请求失败后的重试次数（5xx/429/网络错误）")
    # 规则分类落到兜底（knowledge）时，再用 LLM 判一次意图
    llm_intent_enabled: bool = Field(default=True, description="启用 LLM 意图分类（规则兜底）")
    llm_intent_timeout_seconds: float = Field(default=6.0, description="LLM 意图分类超时秒数")

    # ASR（语音转文字）
    asr_provider: str = "openai"
    asr_api_key: str = ""
    asr_base_url: str = "https://api.openai.com/v1"
    asr_model: str = "whisper-1"
    asr_language: str = "zh"
    # 火山/豆包语音服务新版控制台 APP Key（X-Api-Key 请求头，ASR 与 TTS 共用）
    # 从 https://console.volcengine.com/speech/new/setting/apikeys 获取
    volc_asr_app_key: str = Field(default="", validation_alias="VOLC_ASR_X_API_KEY")
    # 豆包大模型极速版录音识别资源 ID（控制台开通：大模型录音文件识别极速版）
    volc_asr_resource_id: str = Field(default="volc.bigasr.auc_turbo", validation_alias="VOLC_ASR_RESOURCE_ID")

    # TTS（文字转语音，支持慢速）
    tts_provider: str = "openai"
    tts_api_key: str = ""
    tts_base_url: str = "https://api.openai.com/v1"
    tts_model: str = "tts-1"
    tts_voice: str = "alloy"
    tts_speed: float = Field(default=1.0, description="语音语速 0.5-2.0，老年模式建议 0.8")
    # 豆包 SeedTTS 2.0 资源 ID（语音合成控制台音色/实例 ID）
    tts_seedtts_resource_id: str = Field(default="", validation_alias="TTS_SEEDTTS_RESOURCE_ID")

    # 数字人（魔珐星云）运行时配置
    # 注意：星云 SDK 要求 appSecret 出现在浏览器中，属公开凭据；
    # 放在后端只为避免内联进静态产物，并支持不重新构建前端即轮换密钥。
    xingyun_app_id: str = ""
    xingyun_app_secret: str = ""
    xingyun_gateway: str = "https://nebula-agent.xingyun3d.com/user/v1/ttsa/session"

    # 会话
    session_timeout_minutes: int = 60
    max_message_length: int = Field(default=2000, description="单条消息最大字符数，超出截断")
    agent_timeout_seconds: int = Field(default=30, description="Agent 运行超时秒数")
    max_upload_mb: int = Field(default=10, description="音频上传大小上限（MB）")

    # 安全与限流
    admin_token: str = Field(
        default="",
        description="运维接口（如重建索引）的管理员令牌；为空时仅允许本机访问",
    )
    rate_limit_per_minute: int = Field(
        default=60, description="单个客户端每分钟允许的消息/音频请求数，0 表示不限流"
    )
    # 日志
    log_level: str = "INFO"
    log_file: str = "./logs/bridge.log"

    @model_validator(mode="after")
    def _sync_volc_keys(self) -> Settings:
        """火山语音 APP Key（X-Api-Key）在 ASR 与 TTS 之间共用。

        用户只填 VOLC_ASR_X_API_KEY 即可同时启用两个服务；
        若只填了 TTS_API_KEY，也回填给 ASR。
        原实现在模块级直接改单例属性，既绕过校验也需要 type: ignore。
        """
        if not self.volc_asr_app_key and self.tts_api_key:
            self.volc_asr_app_key = self.tts_api_key
        elif (
            self.volc_asr_app_key
            and not self.tts_api_key
            and "openspeech.bytedance.com" in (self.tts_base_url or "")
        ):
            self.tts_api_key = self.volc_asr_app_key
        return self


@lru_cache
def get_settings() -> Settings:
    """获取单例配置。"""
    return Settings()


settings = get_settings()
