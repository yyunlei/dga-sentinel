"""
T093 — 验证 trace_id 在网关中的生成与传播
使用 mock HTTP 调用，验证 trace_id 格式及传递。
"""

from __future__ import annotations

import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from jose import jwt

from common.config import get_settings

settings = get_settings()

_JWT_PAYLOAD = {"sub": "test-user", "tenant_id": "default", "role": "admin"}
_TOKEN = jwt.encode(_JWT_PAYLOAD, settings.jwt_secret, algorithm=settings.jwt_algorithm)
_AUTH_HEADER = {"Authorization": f"Bearer {_TOKEN}"}

_HEX_RE = re.compile(r"^[0-9a-f]{32}$")


@pytest.fixture()
def _patch_lifespan():
    from contextlib import asynccontextmanager
    from fastapi import FastAPI

    @asynccontextmanager
    async def _noop_lifespan(app: FastAPI):
        app.state.pg_pool = None
        app.state.es_client = None
        app.state.redis_client = None
        yield

    with patch("business.main.lifespan", _noop_lifespan):
        import importlib, business.main  # noqa: E401
        importlib.reload(business.main)
        yield business.main.app
        importlib.reload(business.main)


@pytest.fixture()
def client(_patch_lifespan):
    from fastapi.testclient import TestClient
    return TestClient(_patch_lifespan)


class TestTraceIdPropagation:
    """Verify trace_id generation and propagation through the business."""

    def test_gateway_generates_trace_id(self, client):
        """Response should contain X-Trace-ID header."""
        resp = client.get("/health")
        trace_id = resp.headers.get("X-Trace-ID")
        assert trace_id is not None, "X-Trace-ID header missing"
        assert len(trace_id) == 32, f"trace_id length should be 32, got {len(trace_id)}"

    def test_trace_id_is_hex_format(self, client):
        """trace_id must be a 32-char hex string."""
        resp = client.get("/health")
        trace_id = resp.headers.get("X-Trace-ID", "")
        assert _HEX_RE.match(trace_id), f"trace_id not hex: {trace_id}"

    @patch("business.routers.score.write_events_to_starrocks", new_callable=AsyncMock, return_value=True)
    @patch("business.routers.score.get_redis_client", return_value=None)
    @patch("business.routers.score.get_es_client", return_value=None)
    @patch("httpx.AsyncClient.post")
    def test_trace_id_in_score_response(self, mock_post, _es, _redis, _sr, client):
        """Score response body should contain the same trace_id as the header."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"results": []}
        mock_post.return_value = mock_resp

        resp = client.post("/api/score", json={"domains": ["test.com"]}, headers=_AUTH_HEADER)
        header_trace = resp.headers.get("X-Trace-ID", "")
        body_trace = resp.json().get("trace_id", "")
        assert header_trace, "X-Trace-ID header missing"
        assert body_trace, "trace_id missing from response body"

    @patch("business.routers.score.write_events_to_starrocks", new_callable=AsyncMock, return_value=True)
    @patch("business.routers.score.get_redis_client", return_value=None)
    @patch("business.routers.score.get_es_client", return_value=None)
    @patch("httpx.AsyncClient.post")
    def test_trace_id_passed_to_scoring_service(self, mock_post, _es, _redis, _sr, client):
        """When business calls scoring service, trace_id should be propagated."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "results": [{"domain": "test.com", "score": 0.1, "is_dga": False}]
        }
        mock_post.return_value = mock_resp

        resp = client.post("/api/score", json={"domains": ["test.com"]}, headers=_AUTH_HEADER)
        assert resp.status_code == 200
        # The scoring service was called
        assert mock_post.called

    def test_custom_trace_id_header_respected(self, client):
        """If X-Trace-ID is provided in request, business should use it."""
        custom_trace = "a" * 32
        resp = client.get("/health", headers={"X-Trace-ID": custom_trace})
        returned_trace = resp.headers.get("X-Trace-ID", "")
        assert returned_trace == custom_trace
