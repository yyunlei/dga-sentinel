"""RBAC 权限控制 — 基于 JWT claims 的角色权限"""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from gateway.middleware.auth import verify_token
from shared.observability import get_logger

logger = get_logger(__name__)

# Role → allowed route prefixes
ROLE_PERMISSIONS = {
    "admin": {"*"},  # full access
    "analyst": {"/api/score", "/api/alerts", "/api/explain", "/api/feedback", "/api/query", "/api/dag", "/api/operations"},
    "viewer": set(),  # GET only, checked separately
}


class RBACDependency:
    """FastAPI dependency for role-based access control"""

    def __init__(self, allowed_roles: set[str] | None = None, require_write: bool = False):
        self.allowed_roles = allowed_roles or {"admin", "analyst", "viewer"}
        self.require_write = require_write

    async def __call__(self, request: Request, token_data: dict = Depends(verify_token)):
        role = token_data.get("role", "viewer")

        # Admin has full access
        if role == "admin":
            return token_data

        # Check role is allowed
        if role not in self.allowed_roles:
            logger.warning("rbac_denied", role=role, path=request.url.path)
            raise HTTPException(status_code=403, detail=f"Role '{role}' not authorized")

        # Viewer can only do GET
        if role == "viewer" and request.method != "GET":
            raise HTTPException(status_code=403, detail="Viewer role: read-only access")

        # Analyst write check
        if self.require_write and role == "viewer":
            raise HTTPException(status_code=403, detail="Write access required")

        return token_data


# Convenience instances
require_admin = RBACDependency(allowed_roles={"admin"})
require_analyst = RBACDependency(allowed_roles={"admin", "analyst"})
require_viewer = RBACDependency(allowed_roles={"admin", "analyst", "viewer"})
require_write = RBACDependency(allowed_roles={"admin", "analyst"}, require_write=True)
