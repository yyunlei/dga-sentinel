"""M6 测试 — 审计日志中间件"""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from gateway.middleware.audit import AuditMiddleware


class TestAuditMiddleware:
    def test_middleware_init(self):
        app = MagicMock()
        middleware = AuditMiddleware(app)
        assert middleware is not None

    @pytest.mark.asyncio
    async def test_log_audit_fallback(self):
        """When asyncpg.connect raises, _log_audit falls back to logger."""
        app = MagicMock()
        middleware = AuditMiddleware(app)

        with patch("gateway.middleware.audit.logger") as mock_logger, \
             patch.dict("sys.modules", {"asyncpg": MagicMock(
                 connect=AsyncMock(side_effect=Exception("pg unavailable"))
             )}):
            await middleware._log_audit(
                user_id="test_user",
                action="GET",
                resource="/api/score",
                detail="{}",
                ip="127.0.0.1",
            )
            mock_logger.info.assert_called_once_with(
                "audit_log",
                user_id="test_user",
                action="GET",
                resource="/api/score",
                ip="127.0.0.1",
            )
