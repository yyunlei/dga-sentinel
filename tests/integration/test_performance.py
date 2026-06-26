"""
T094 — 性能验证测试（mock-based，验证逻辑而非实际耗时）
验证评分端点响应、批量处理、缓存加速、批量上限。
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from jose import jwt

from common.config import get_settings

settings = get_settings()

_JWT_PAYLOAD = {"sub": "test-user", "tenant_id": "default", "role": "admin"}
_TOKEN = jwt.encode(_JWT_PAYLOAD, settings.jwt_secret, algorithm=settings.jwt_algorithm)
_AUTH_HEADER = {"Authorization": f"Bearer {_TOKEN}"}


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


def _make_score_mock(domains: list[str]) -> MagicMock:
    """Build a mock httpx response for scoring service."""
    results = [
        {"domain": d, "score": 0.1, "is_dga": False, "family": None,
         "family_confidence": None, "model_version": "v1", "cached": False}
        for d in domains
    ]
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"results": results}
    return mock_resp


class TestPerformance:
    """Mock-based performance validation."""

    @patch("business.api.score.write_events_to_starrocks", new_callable=AsyncMock, return_value=True)
    @patch("business.api.score.get_redis_client", return_value=None)
    @patch("business.api.score.get_es_client", return_value=None)
    @patch("httpx.AsyncClient.post")
    def test_single_domain_scoring_responds(self, mock_post, _es, _redis, _sr, client):
        """Single domain scoring endpoint should return 200."""
        mock_post.return_value = _make_score_mock(["test.com"])
        resp = client.post("/api/score", json={"domains": ["test.com"]}, headers=_AUTH_HEADER)
        assert resp.status_code == 200
        assert resp.json()["results"] is not None

    @patch("business.api.score.write_events_to_starrocks", new_callable=AsyncMock, return_value=True)
    @patch("business.api.score.get_redis_client", return_value=None)
    @patch("business.api.score.get_es_client", return_value=None)
    @patch("httpx.AsyncClient.post")
    def test_batch_1000_domains_accepted(self, mock_post, _es, _redis, _sr, client):
        """Batch of 1000 domains should be accepted (max allowed)."""
        domains = [f"domain{i}.com" for i in range(1000)]
        mock_post.return_value = _make_score_mock(domains)
        resp = client.post("/api/score", json={"domains": domains}, headers=_AUTH_HEADER)
        assert resp.status_code == 200

    @patch("business.api.score.write_events_to_starrocks", new_callable=AsyncMock, return_value=True)
    @patch("httpx.AsyncClient.post")
    def test_redis_cache_avoids_scoring_call(self, mock_post, _sr, _patch_lifespan):
        """When all domains are cached in Redis, scoring service should not be called."""
        from fastapi.testclient import TestClient
        from business.repositories.pg_repo import get_es_client, get_redis_client

        cached = json.dumps({
            "domain": "cached.com", "score": 0.2, "is_dga": False,
            "family": None, "family_confidence": None, "model_version": "v1", "cached": True,
        })
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=cached)
        mock_redis.set = AsyncMock()

        _patch_lifespan.dependency_overrides[get_es_client] = lambda: None
        _patch_lifespan.dependency_overrides[get_redis_client] = lambda: mock_redis
        try:
            tc = TestClient(_patch_lifespan)
            resp = tc.post("/api/score", json={"domains": ["cached.com"]}, headers=_AUTH_HEADER)
            assert resp.status_code == 200
            mock_post.assert_not_called()
        finally:
            _patch_lifespan.dependency_overrides.clear()

    def test_batch_exceeds_limit_returns_error(self, client):
        """Batch size > 1000 should be rejected (422 from Pydantic or 400 from handler)."""
        domains = [f"d{i}.com" for i in range(1001)]
        resp = client.post("/api/score", json={"domains": domains}, headers=_AUTH_HEADER)
        assert resp.status_code in (400, 422)

    @patch("business.api.score.write_events_to_starrocks", new_callable=AsyncMock, return_value=True)
    @patch("business.api.score.get_redis_client", return_value=None)
    @patch("business.api.score.get_es_client", return_value=None)
    @patch("httpx.AsyncClient.post")
    def test_response_includes_latency(self, mock_post, _es, _redis, _sr, client):
        """Response should include latency_ms field."""
        mock_post.return_value = _make_score_mock(["test.com"])
        resp = client.post("/api/score", json={"domains": ["test.com"]}, headers=_AUTH_HEADER)
        body = resp.json()
        assert "latency_ms" in body
        assert isinstance(body["latency_ms"], (int, float))

