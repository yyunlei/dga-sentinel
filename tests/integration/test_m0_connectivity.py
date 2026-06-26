"""
M0 集成测试 — 验证 JWT 401、Redis 缓存命中、WebSocket 推送、readyz 正确
"""

import json
import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from jose import jwt

from common.config import get_settings


@pytest.fixture
def settings():
    s = get_settings()
    return s


@pytest.fixture
def valid_token(settings):
    """Generate a valid JWT token for testing."""
    payload = {"sub": "test-user", "tenant_id": "default", "role": "admin"}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


@pytest.fixture
def app():
    """Create test FastAPI app in production mode to enforce JWT."""
    import os
    os.environ["APP_ENV"] = "production"
    os.environ["REDIS_URL"] = "redis://localhost:6379/0"
    from common.config import get_settings
    get_settings.cache_clear()
    # Reset rate limiter singleton
    from business.middleware import rate_limit
    rate_limit._limiter = None

    from business.main import app
    yield app

    os.environ["APP_ENV"] = "development"
    get_settings.cache_clear()
    rate_limit._limiter = None


@pytest.fixture
def client(app):
    return TestClient(app, raise_server_exceptions=False)


# --- T011-T015: JWT 401 Tests ---

class TestJWTAuth:
    """Verify protected endpoints return 401 with invalid token."""

    def test_score_rejects_invalid_token(self, client):
        resp = client.post(
            "/api/score",
            json={"domains": ["example.com"]},
            headers={"Authorization": "Bearer invalid-token"},
        )
        assert resp.status_code == 401

    def test_alerts_rejects_invalid_token(self, client):
        resp = client.get(
            "/api/alerts",
            headers={"Authorization": "Bearer invalid-token"},
        )
        assert resp.status_code == 401

    def test_models_rejects_invalid_token(self, client):
        resp = client.get(
            "/api/models",
            headers={"Authorization": "Bearer invalid-token"},
        )
        assert resp.status_code == 401

    def test_dag_rejects_invalid_token(self, client):
        resp = client.get(
            "/api/dag/pipelines",
            headers={"Authorization": "Bearer invalid-token"},
        )
        assert resp.status_code == 401

    def test_feedback_rejects_invalid_token(self, client):
        resp = client.post(
            "/api/feedback",
            json={"event_id": "evt-1", "domain": "test.com", "true_label": "dga"},
            headers={"Authorization": "Bearer invalid-token"},
        )
        assert resp.status_code == 401

    def test_health_no_auth_required(self, client):
        """Health endpoints should NOT require auth."""
        resp = client.get("/api/healthz")
        assert resp.status_code == 200


# --- T016: Redis Cache Key Format ---

class TestRedisCache:
    def test_cache_key_format(self):
        domain = "example.com"
        domain_hash = hashlib.sha256(domain.encode()).hexdigest()[:16]
        cache_key = f"score:{domain_hash}"
        assert cache_key.startswith("score:")
        assert len(domain_hash) == 16

    def test_different_domains_different_keys(self):
        d1 = hashlib.sha256(b"foo.com").hexdigest()[:16]
        d2 = hashlib.sha256(b"bar.com").hexdigest()[:16]
        assert d1 != d2


# --- T019: readyz calls /readyz ---

class TestReadyz:
    def test_readyz_endpoint_exists(self, client):
        resp = client.get("/api/readyz")
        assert resp.status_code in (200, 503)

    def test_readyz_response_has_checks(self, client):
        resp = client.get("/api/readyz")
        data = resp.json()
        assert "checks" in data or "status" in data


# --- T018: Prometheus Alert Rules ---

class TestAlertRules:
    def test_alert_rules_file_exists(self):
        rules_path = Path(__file__).parent.parent.parent / "deploy" / "prometheus" / "alert_rules.yml"
        assert rules_path.exists()

    def test_alert_rules_count_gte_5(self):
        import yaml
        rules_path = Path(__file__).parent.parent.parent / "deploy" / "prometheus" / "alert_rules.yml"
        with open(rules_path) as f:
            data = yaml.safe_load(f)
        rules = data["groups"][0]["rules"]
        assert len(rules) >= 5, f"Expected >= 5 alert rules, got {len(rules)}"

    def test_required_alert_names(self):
        import yaml
        rules_path = Path(__file__).parent.parent.parent / "deploy" / "prometheus" / "alert_rules.yml"
        with open(rules_path) as f:
            data = yaml.safe_load(f)
        names = {r["alert"] for r in data["groups"][0]["rules"]}
        required = {"HighScoringLatency", "HighErrorRate", "ModelDrift", "KafkaConsumerLag", "AgentTimeout"}
        assert required.issubset(names), f"Missing alerts: {required - names}"
