from __future__ import annotations

import os

from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from shared.config import get_settings
from shared.observability import AUTH_FAILURES

security = HTTPBearer(auto_error=False)


async def verify_token(
    credentials: HTTPAuthorizationCredentials | None = Security(security),
) -> dict:
    """验证 JWT token，返回 payload"""
    settings = get_settings()

    # 开发模式跳过认证（需同时满足 is_dev 和 ALLOW_DEV_AUTH 环境变量）
    if settings.is_dev and credentials is None:
        if os.environ.get("ALLOW_DEV_AUTH", "true").lower() == "true":
            return {"sub": "dev", "tenant_id": "default", "role": "admin"}

    if credentials is None:
        AUTH_FAILURES.labels(reason="missing_token").inc()
        raise HTTPException(401, "Missing authorization token")

    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
        return payload
    except JWTError as e:
        AUTH_FAILURES.labels(reason="invalid_token").inc()
        raise HTTPException(401, "Invalid token")
