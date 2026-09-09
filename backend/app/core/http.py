"""进程级共享 httpx.AsyncClient。

所有外部服务适配器（LLM/ASR/TTS/翻译）复用同一连接池，
避免每次调用新建客户端造成的 TCP/TLS 握手开销与句柄泄漏。
应用关闭时由 lifespan 统一 aclose。
"""

from __future__ import annotations

import httpx

_shared_client: httpx.AsyncClient | None = None


def get_http_client() -> httpx.AsyncClient:
    """获取共享 AsyncClient（懒创建，进程级单例）。

    默认超时 60s；单个请求可用 `timeout=` 参数覆盖，例如 ASR 长音频 120s。
    """
    global _shared_client
    if _shared_client is None or _shared_client.is_closed:
        _shared_client = httpx.AsyncClient(
            timeout=60.0,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
    return _shared_client


async def close_http_client() -> None:
    """应用关闭时释放连接池。"""
    global _shared_client
    if _shared_client is not None and not _shared_client.is_closed:
        await _shared_client.aclose()
    _shared_client = None
