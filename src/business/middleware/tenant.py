"""
租户隔离中间件
"""

from __future__ import annotations

from fastapi import Request


def get_tenant_id(request: Request) -> str:
    """从请求中提取租户 ID"""
    # 优先从 header 获取
    tenant = request.headers.get("X-Tenant-ID")
    if tenant:
        return tenant
    # 从 JWT payload 获取
    if hasattr(request.state, "user") and isinstance(request.state.user, dict):
        return request.state.user.get("tenant_id", "default")
    return "default"
