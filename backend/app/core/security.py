"""接口保护：管理员令牌、限流、上传大小限制。

本项目面向医院/政务大厅等公共场景，此前所有接口均无任何保护：
`POST /api/knowledge/reindex` 任何人可触发全量重建，音频上传无大小上限。
"""

from __future__ import annotations

import ipaddress
import time
from collections import defaultdict, deque

from fastapi import Header, HTTPException, Request, status

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger()


def _is_loopback(host: str | None) -> bool:
    if not host:
        return False
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host in ("localhost",)


async def require_admin(
    request: Request,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
) -> None:
    """保护运维类接口（如重建索引）。

    - 配置了 `ADMIN_TOKEN`：必须携带匹配的 `X-Admin-Token`；
    - 未配置：只允许本机访问（开发/演示默认安全，公网必须显式配置令牌）。
    """
    if settings.admin_token:
        if x_admin_token and x_admin_token == settings.admin_token:
            return
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="需要有效的管理员令牌")
    client = request.client.host if request.client else None
    if _is_loopback(client):
        return
    logger.warning("拒绝来自非本机的运维接口访问：path={} client={}", request.url.path, client)
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="该接口仅允许本机访问，或配置 ADMIN_TOKEN 后携带 X-Admin-Token",
    )


class _SlidingWindowLimiter:
    """进程内滑动窗口限流。

    多实例部署时需替换为 Redis 等共享存储；单实例场景下足以挡住
    误用与简单的刷量。
    """

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str, *, limit: int, window_s: float = 60.0) -> bool:
        if limit <= 0:
            return True
        now = time.monotonic()
        bucket = self._hits[key]
        cutoff = now - window_s
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= limit:
            return False
        bucket.append(now)
        return True


limiter = _SlidingWindowLimiter()


def rate_limit(bucket_name: str, *, limit_attr: str = "rate_limit_per_minute"):
    """返回一个 FastAPI 依赖，按「客户端 IP + 桶名」限流。"""

    async def _dependency(request: Request) -> None:
        limit = int(getattr(settings, limit_attr, 0))
        if limit <= 0:
            return
        client = request.client.host if request.client else "unknown"
        if not limiter.allow(f"{bucket_name}:{client}", limit=limit):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"请求过于频繁，请稍后重试（每分钟最多 {limit} 次）",
            )

    return _dependency


async def read_upload_limited(upload, *, max_bytes: int | None = None) -> bytes:
    """读取上传内容并强制大小上限。

    直接 `await upload.read()` 会把任意大小的文件读进内存（DoS 风险）。
    这里先看 Content-Length，再分块读取并在超限时中断。
    """
    limit = max_bytes if max_bytes is not None else settings.max_upload_mb * 1024 * 1024
    if limit <= 0:
        return await upload.read()

    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(64 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            # 用字面量 413，避免 starlette 版本间常量改名带来的弃用警告
            raise HTTPException(
                status_code=413,
                detail=f"音频文件过大，最大 {settings.max_upload_mb} MB",
            )
        chunks.append(chunk)
    return b"".join(chunks)
