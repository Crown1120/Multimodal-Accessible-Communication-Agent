"""请求上下文中间件：request_id 传播 + 访问日志。

此前 `logging.request_id_var` 定义了但没有任何地方设置，日志里 `request_id`
恒为 "-"，链路追踪形同虚设；也没有任何访问日志（方法/路径/状态码/耗时）。
"""

from __future__ import annotations

import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import get_logger, request_id_var

logger = get_logger()

_REQUEST_ID_HEADER = "X-Request-ID"


class RequestContextMiddleware(BaseHTTPMiddleware):
    """为每个请求分配 request_id，并记录访问日志。"""

    async def dispatch(self, request: Request, call_next) -> Response:
        # 优先复用上游（nginx / 网关）传入的 request_id，便于跨服务串联
        request_id = request.headers.get(_REQUEST_ID_HEADER) or uuid.uuid4().hex[:16]
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers[_REQUEST_ID_HEADER] = request_id
            return response
        finally:
            duration_ms = (time.perf_counter() - started) * 1000
            client = request.client.host if request.client else "-"
            # SSE 长连接耗时很长，用 debug 级别避免刷屏
            log = logger.debug if request.url.path.endswith("/events") else logger.info
            log(
                "{} {} -> {} {:.0f}ms client={}",
                request.method,
                request.url.path,
                status_code,
                duration_ms,
                client,
            )
            request_id_var.reset(token)
