"""
business 中间件单元测试 — 限流 + JWT 认证
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from business.middleware.rate_limit import InMemoryRateLimiter


# ── InMemoryRateLimiter ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_rate_limiter_allows_within_limit():
    limiter = InMemoryRateLimiter(max_requests=3, window_seconds=60)
    assert await limiter.check("client-1") is True
    assert await limiter.check("client-1") is True
    assert await limiter.check("client-1") is True


@pytest.mark.asyncio
async def test_rate_limiter_rejects_over_limit():
    limiter = InMemoryRateLimiter(max_requests=2, window_seconds=60)
    assert await limiter.check("client-1") is True
    assert await limiter.check("client-1") is True
    assert await limiter.check("client-1") is False


@pytest.mark.asyncio
async def test_rate_limiter_isolates_keys():
    limiter = InMemoryRateLimiter(max_requests=1, window_seconds=60)
    assert await limiter.check("client-a") is True
    assert await limiter.check("client-b") is True
    assert await limiter.check("client-a") is False


@pytest.mark.asyncio
async def test_rate_limiter_custom_limit():
    limiter = InMemoryRateLimiter(max_requests=10, window_seconds=60)
    assert await limiter.check("client-1", limit=1) is True
    assert await limiter.check("client-1", limit=1) is False


# ── JWT verify_token ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_verify_token_dev_mode_no_credentials():
    """开发模式下无 token 返回默认 payload"""
    with patch("gateway.middleware.auth.get_settings") as mock_settings:
        mock_settings.return_value = MagicMock(is_dev=True)
        from business.middleware.auth import verify_token
        result = await verify_token(credentials=None)
        assert result == {"sub": "dev", "tenant_id": "default"}


@pytest.mark.asyncio
async def test_verify_token_missing_in_prod():
    """生产模式下无 token 抛 401"""
    with patch("gateway.middleware.auth.get_settings") as mock_settings:
        mock_settings.return_value = MagicMock(is_dev=False)
        from fastapi import HTTPException
        from business.middleware.auth import verify_token
        with pytest.raises(HTTPException) as exc_info:
            await verify_token(credentials=None)
        assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_verify_token_invalid_jwt():
    """无效 JWT 抛 401"""
    with patch("gateway.middleware.auth.get_settings") as mock_settings:
        mock_settings.return_value = MagicMock(
            is_dev=False, jwt_secret="test-secret", jwt_algorithm="HS256"
        )
        from fastapi import HTTPException
        from fastapi.security import HTTPAuthorizationCredentials
        from business.middleware.auth import verify_token

        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="invalid.token.here")
        with pytest.raises(HTTPException) as exc_info:
            await verify_token(credentials=creds)
        assert exc_info.value.status_code == 401
