"""M6 测试 — RBAC 角色权限校验"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock
from fastapi import HTTPException

from gateway.middleware.rbac import (
    RBACDependency,
    ROLE_PERMISSIONS,
    require_admin,
    require_analyst,
    require_viewer,
)


class TestRBACDependency:
    @pytest.fixture
    def mock_request(self):
        req = MagicMock()
        req.url.path = "/api/score"
        req.method = "POST"
        return req

    @pytest.mark.asyncio
    async def test_admin_full_access(self, mock_request):
        dep = RBACDependency()
        result = await dep(mock_request, {"role": "admin", "sub": "user1"})
        assert result["role"] == "admin"

    @pytest.mark.asyncio
    async def test_analyst_allowed(self, mock_request):
        dep = RBACDependency(allowed_roles={"admin", "analyst"})
        result = await dep(mock_request, {"role": "analyst", "sub": "user2"})
        assert result["role"] == "analyst"

    @pytest.mark.asyncio
    async def test_viewer_read_only(self, mock_request):
        """Viewer passes GET but fails POST."""
        dep = RBACDependency()
        # GET should pass
        mock_request.method = "GET"
        result = await dep(mock_request, {"role": "viewer", "sub": "user3"})
        assert result["role"] == "viewer"
        # POST should fail
        mock_request.method = "POST"
        with pytest.raises(HTTPException) as exc:
            await dep(mock_request, {"role": "viewer", "sub": "user3"})
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_viewer_denied_write(self, mock_request):
        dep = RBACDependency(require_write=True)
        mock_request.method = "POST"
        with pytest.raises(HTTPException) as exc:
            await dep(mock_request, {"role": "viewer", "sub": "user3"})
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_unknown_role_denied(self, mock_request):
        dep = RBACDependency(allowed_roles={"admin", "analyst"})
        with pytest.raises(HTTPException) as exc:
            await dep(mock_request, {"role": "unknown", "sub": "user4"})
        assert exc.value.status_code == 403


class TestRolePermissions:
    def test_admin_has_wildcard(self):
        assert "*" in ROLE_PERMISSIONS["admin"]

    def test_analyst_permissions(self):
        expected = {"/api/score", "/api/alerts", "/api/explain", "/api/feedback"}
        assert expected.issubset(ROLE_PERMISSIONS["analyst"])

    def test_viewer_empty_permissions(self):
        assert ROLE_PERMISSIONS["viewer"] == set()
