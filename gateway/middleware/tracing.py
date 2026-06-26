"""
trace_id 注入中间件 — 支持 OpenTelemetry context 提取
"""

from __future__ import annotations

from uuid import uuid4

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


def _get_otel_trace_id() -> str | None:
    """尝试从 OTel context 提取 trace_id"""
    try:
        from opentelemetry import trace
        span = trace.get_current_span()
        ctx = span.get_span_context()
        if ctx and ctx.trace_id:
            return format(ctx.trace_id, '032x')
    except (ImportError, Exception):
        pass
    return None


class TracingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # 跳过 WebSocket 连接（WebSocket 不是 HTTP 请求/响应）
        if request.url.path.startswith("/api/ws/"):
            return await call_next(request)
        # 优先使用 OTel trace_id，其次 header，最后生成新的
        trace_id = _get_otel_trace_id() or request.headers.get("X-Trace-ID") or uuid4().hex
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(trace_id=trace_id)

        request.state.trace_id = trace_id
        response = await call_next(request)
        response.headers["X-Trace-ID"] = trace_id
        return response
