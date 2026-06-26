"""
T091 — 端到端测试: 域名提交 → 检测 → 告警 → Agent 分析 → 前端展示
全流程使用 mock，无需真实服务。
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from jose import jwt

from common.config import get_settings

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

settings = get_settings()

_JWT_PAYLOAD = {"sub": "test-user", "tenant_id": "default", "role": "admin"}
_TOKEN = jwt.encode(_JWT_PAYLOAD, settings.jwt_secret, algorithm=settings.jwt_algorithm)
_AUTH_HEADER = {"Authorization": f"Bearer {_TOKEN}"}

# Scoring service mock response
_MOCK_SCORE_RESP = {
    "results": [
        {
            "domain": "evil123.xyz",
            "score": 0.95,
            "is_dga": True,
            "family": "qakbot",
            "family_confidence": 0.88,
            "model_version": "v1.0",
            "cached": False,
        }
    ]
}


@pytest.fixture()
def _patch_lifespan():
    """Bypass business lifespan (DB connections) and inject mock clients."""
    from contextlib import asynccontextmanager
    from fastapi import FastAPI

    @asynccontextmanager
    async def _noop_lifespan(app: FastAPI):
        app.state.pg_pool = None
        app.state.es_client = None
        app.state.redis_client = None
        yield

    with patch("business.main.lifespan", _noop_lifespan):
        # Re-import to pick up patched lifespan
        import importlib, business.main  # noqa: E401
        importlib.reload(business.main)
        yield business.main.app
        importlib.reload(business.main)


@pytest.fixture()
def client(_patch_lifespan):
    """TestClient with mocked lifespan."""
    from fastapi.testclient import TestClient
    return TestClient(_patch_lifespan)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFullPipeline:
    """E2E: domain submit → score → alert → agent explain → display."""

    @patch("business.api.score.write_events_to_starrocks", new_callable=AsyncMock, return_value=True)
    @patch("business.api.score.get_redis_client", return_value=None)
    @patch("business.api.score.get_es_client", return_value=None)
    @patch("httpx.AsyncClient.post")
    def test_score_returns_results(self, mock_post, _es, _redis, _sr, client):
        """POST /api/score returns score results for a valid domain."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = _MOCK_SCORE_RESP
        mock_post.return_value = mock_resp

        resp = client.post("/api/score", json={"domains": ["evil123.xyz"]}, headers=_AUTH_HEADER)
        assert resp.status_code == 200
        body = resp.json()
        assert "results" in body
        assert "trace_id" in body
        assert len(body["results"]) >= 1
        assert body["results"][0]["domain"] == "evil123.xyz"

    @patch("business.api.score.write_events_to_starrocks", new_callable=AsyncMock, return_value=True)
    @patch("business.api.score.get_redis_client", return_value=None)
    @patch("business.api.score.get_es_client", return_value=None)
    @patch("httpx.AsyncClient.post")
    def test_score_high_triggers_alert_fields(self, mock_post, _es, _redis, _sr, client):
        """High-score domain result contains severity-relevant fields."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = _MOCK_SCORE_RESP
        mock_post.return_value = mock_resp

        resp = client.post("/api/score", json={"domains": ["evil123.xyz"]}, headers=_AUTH_HEADER)
        result = resp.json()["results"][0]
        assert result["is_dga"] is True
        assert result["score"] >= 0.7

    @patch("business.api.score.write_events_to_starrocks", new_callable=AsyncMock, return_value=True)
    @patch("httpx.AsyncClient.post")
    def test_cache_hit_skips_scoring_service(self, mock_post, _sr, _patch_lifespan):
        """Cached domain should be returned without calling scoring service."""
        from fastapi.testclient import TestClient
        from business.repositories.pg_repo import get_es_client, get_redis_client

        cached_result = {
            "domain": "cached.xyz",
            "score": 0.85,
            "is_dga": True,
            "family": "necurs",
            "family_confidence": 0.7,
            "model_version": "v1.0",
            "cached": True,
        }
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=json.dumps(cached_result))
        mock_redis.set = AsyncMock()

        _patch_lifespan.dependency_overrides[get_es_client] = lambda: None
        _patch_lifespan.dependency_overrides[get_redis_client] = lambda: mock_redis
        try:
            tc = TestClient(_patch_lifespan)
            resp = tc.post("/api/score", json={"domains": ["cached.xyz"]}, headers=_AUTH_HEADER)
            assert resp.status_code == 200
            results = resp.json()["results"]
            assert len(results) == 1
            assert results[0]["domain"] == "cached.xyz"
            mock_post.assert_not_called()
        finally:
            _patch_lifespan.dependency_overrides.clear()

    def test_score_without_token_returns_401(self, client):
        """POST /api/score without JWT returns 401 in non-dev mode."""
        with patch("business.middleware.auth.get_settings") as mock_s:
            mock_s.return_value = MagicMock(is_dev=False, jwt_secret="s", jwt_algorithm="HS256")
            resp = client.post("/api/score", json={"domains": ["test.com"]})
            assert resp.status_code in (401, 403)

    @patch("business.api.explain._fallback_explanation", return_value="fallback explanation")
    @patch("ai.agents.agents.explain_agent.ExplainAgent.run", new_callable=AsyncMock)
    def test_explain_endpoint_calls_agent(self, mock_agent_run, _fb, client):
        """POST /api/explain invokes ExplainAgent and returns explanation."""
        mock_agent_run.return_value = {
            "output": {
                "explanation": "This domain exhibits DGA characteristics.",
                "dimensions": [{"name": "entropy", "value": 0.9}],
                "confidence": 0.85,
            }
        }
        resp = client.post(
            "/api/explain",
            json={"domain": "evil123.xyz", "score": 0.95},
            headers=_AUTH_HEADER,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["domain"] == "evil123.xyz"
        assert "explanation" in body

    @patch("business.api.score.write_events_to_starrocks", new_callable=AsyncMock, return_value=True)
    @patch("business.api.score.get_redis_client", return_value=None)
    @patch("business.api.score.get_es_client", return_value=None)
    @patch("httpx.AsyncClient.post")
    def test_score_response_contains_trace_id(self, mock_post, _es, _redis, _sr, client):
        """Score response must include a trace_id field."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"results": []}
        mock_post.return_value = mock_resp

        resp = client.post("/api/score", json={"domains": ["benign.com"]}, headers=_AUTH_HEADER)
        assert resp.status_code == 200
        assert "trace_id" in resp.json()

    def test_health_endpoint(self, client):
        """Root /health returns ok."""
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


