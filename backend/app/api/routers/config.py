"""公开运行时配置。

用于把「必须出现在浏览器里」的第三方凭据从静态产物中移出：
前端构建时不再内联星云 appSecret，而是在运行时向后端取。
运营侧轮换密钥时无需重新构建前端。

安全说明：星云 SDK 的设计要求 appSecret 出现在浏览器中
（见 https://xingyun3d.com/developers/59-502 ），因此该值对终端用户
本质上是公开的。生产环境必须使用「域名白名单 + 配额限制」的专用密钥，
不要复用其它系统的密钥。
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import settings

router = APIRouter()


class PublicConfig(BaseModel):
    xingyun_app_id: str = ""
    xingyun_app_secret: str = ""
    xingyun_gateway: str = ""
    # 前端据此设置输入框 maxlength，避免用户输入被静默截断
    max_message_length: int = 2000
    max_upload_mb: int = 10


@router.get("/config/public", response_model=PublicConfig, summary="公开运行时配置")
async def public_config() -> PublicConfig:
    return PublicConfig(
        xingyun_app_id=settings.xingyun_app_id,
        xingyun_app_secret=settings.xingyun_app_secret,
        xingyun_gateway=settings.xingyun_gateway,
        max_message_length=settings.max_message_length,
        max_upload_mb=settings.max_upload_mb,
    )
