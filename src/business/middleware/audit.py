"""审计日志中间件 — 所有 API 调用记录到 PG audit_log"""
from __future__ import annotations

import asyncio
import json
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from common.config import get_settings
from common.observability import get_logger

logger = get_logger(__name__)


class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.time()
        response = await call_next(request)
        duration_ms = (time.time() - start) * 1000

        # Extract user info from request state (set by auth middleware)
        user_id = getattr(request.state, "user_id", "anonymous")

        # Non-blocking audit log
        asyncio.create_task(self._log_audit(
            user_id=user_id,
            action=request.method,
            resource=str(request.url.path),
            detail=json.dumps({
                "status_code": response.status_code,
                "duration_ms": round(duration_ms, 2),
                "query_params": str(request.query_params),
            }),
            ip=request.client.host if request.client else "unknown",
        ))
        return response

    async def _log_audit(self, user_id: str, action: str, resource: str, detail: str, ip: str):
        try:
            from business.db import _pg_pool
            if _pg_pool:
                await _pg_pool.execute(
                    "INSERT INTO audit_log (user_id, action, resource, detail, ip_address) VALUES ($1, $2, $3, $4, $5)",
                    user_id, action, resource, detail, ip,
                )
            else:
                logger.info("audit_log", user_id=user_id, action=action, resource=resource, ip=ip)
        except Exception as e:
            # Fallback to structured logging
            logger.info("audit_log", user_id=user_id, action=action, resource=resource, ip=ip)
