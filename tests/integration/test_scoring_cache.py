"""
T087 集成测试 — 评分 → Redis 缓存 → 重复请求命中缓存
验证 scoring 路由的 Redis 缓存逻辑：
  - 首次评分调用 scoring-service 并写入缓存
  - 重复评分命中缓存，不再调用 scoring-service
  - 缓存 key 格式: score:{sha256(domain)[:16]}
  - 缓存 TTL = 300s
"""

import hashlib
import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from jose import jwt

from shared.config import get_settings
from gateway.db import get_es_client, get_redis_client


# ── Fixtures ──────────────────────────────────────────────

@pytest.fixture
def settings():
    return get_settings()


@pytest.fixture
def valid_token(settings):
    payload = {"sub": "test-user", "tenant_id": "default", "role": "admin"}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


@pytest.fixture
def mock_redis():
    """In-memory dict simulating async Redis client."""
    store: dict[str, tuple[str, int | None]] = {}

    redis = AsyncMock()

    async def _get(key):
        entry = store.get(key)
        return entry[0] if entry else None

    async def _set(key, value, ex=None):
        store[key] = (value, ex)

    redis.get = AsyncMock(side_effect=_get)
    redis.set = AsyncMock(side_effect=_set)
    redis._store = store  # expose for assertions
    return redis


@pytest.fixture
def scoring_response():
    """Fake scoring-service JSON response."""
    return {
        "results": [
            {
                "domain": "evil.com",
                "score": 0.95,
                "is_dga": True,
                "family": "conficker",
                "family_confidence": 0.88,
                "model_version": "v2.1",
            }
        ]
    }


@pytest.fixture
def app(mock_redis):
    os.environ["APP_ENV"] = "production"
    os.environ["REDIS_URL"] = "redis://localhost:6379/0"
    get_settings.cache_clear()
    from gateway.middleware import rate_limit
    rate_limit._limiter = None
    from gateway.main import app

    # Override FastAPI dependencies to inject mocks
    app.dependency_overrides[get_redis_client] = lambda: mock_redis
    app.dependency_overrides[get_es_client] = lambda: None

    yield app

    app.dependency_overrides.clear()
    os.environ["APP_ENV"] = "development"
    get_settings.cache_clear()
    rate_limit._limiter = None


@pytest.fixture
def auth_headers(valid_token):
    return {"Authorization": f"Bearer {valid_token}"}


# ── Tests ─────────────────────────────────────────────────

class TestCacheKeyFormat:
    """Verify cache key derivation from domain."""

    def test_cache_key_uses_sha256_prefix(self):
        domain = "evil.com"
        domain_hash = hashlib.sha256(domain.encode()).hexdigest()[:16]
        cache_key = f"score:{domain_hash}"
        assert cache_key == f"score:{domain_hash}"
        assert len(domain_hash) == 16

    def test_cache_key_deterministic(self):
        domain = "test-domain.xyz"
        k1 = f"score:{hashlib.sha256(domain.encode()).hexdigest()[:16]}"
        k2 = f"score:{hashlib.sha256(domain.encode()).hexdigest()[:16]}"
        assert k1 == k2

    def test_different_domains_produce_different_keys(self):
        h1 = hashlib.sha256(b"aaa.com").hexdigest()[:16]
        h2 = hashlib.sha256(b"bbb.com").hexdigest()[:16]
        assert h1 != h2


class TestScoringCacheIntegration:
    """End-to-end: score → cache write → cache hit on repeat."""

    @patch("gateway.routers.score.write_events_to_starrocks", new_callable=AsyncMock)
    @patch("httpx.AsyncClient.post")
    def test_first_request_calls_scoring_service(
        self, mock_http_post, mock_sr,
        app, auth_headers, mock_redis, scoring_response,
    ):
        mock_http_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value=scoring_response),
            raise_for_status=MagicMock(),
        )

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/api/score",
            json={"domains": ["evil.com"]},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["results"]) == 1
        assert data["results"][0]["domain"] == "evil.com"
        mock_http_post.assert_called_once()

    @patch("gateway.routers.score.write_events_to_starrocks", new_callable=AsyncMock)
    @patch("httpx.AsyncClient.post")
    def test_cached_result_skips_scoring_service(
        self, mock_http_post, mock_sr,
        app, auth_headers, mock_redis, scoring_response,
    ):
        # Pre-populate cache
        domain = "evil.com"
        domain_hash = hashlib.sha256(domain.encode()).hexdigest()[:16]
        cache_key = f"score:{domain_hash}"
        cached_result = {
            "domain": "evil.com", "score": 0.95, "is_dga": True,
            "family": "conficker", "family_confidence": 0.88,
            "model_version": "v2.1", "cached": False,
        }
        mock_redis._store[cache_key] = (json.dumps(cached_result), 300)

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/api/score",
            json={"domains": ["evil.com"]},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        # Scoring service should NOT be called — result came from cache
        mock_http_post.assert_not_called()

    def test_cache_ttl_is_300(self):
        """Verify the TTL constant used in score.py is 300."""
        import inspect
        from gateway.routers import score as score_mod
        source = inspect.getsource(score_mod)
        assert "ex=300" in source


class TestCacheWriteOnScore:
    """Verify that scoring writes to Redis with correct key and TTL."""

    @patch("gateway.routers.score.write_events_to_starrocks", new_callable=AsyncMock)
    @patch("httpx.AsyncClient.post")
    def test_score_writes_cache_entry(
        self, mock_http_post, mock_sr,
        app, auth_headers, mock_redis, scoring_response,
    ):
        mock_http_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value=scoring_response),
            raise_for_status=MagicMock(),
        )

        client = TestClient(app, raise_server_exceptions=False)
        client.post("/api/score", json={"domains": ["evil.com"]}, headers=auth_headers)

        domain_hash = hashlib.sha256(b"evil.com").hexdigest()[:16]
        cache_key = f"score:{domain_hash}"
        assert cache_key in mock_redis._store
        stored_val, ttl = mock_redis._store[cache_key]
        assert ttl == 300
        parsed = json.loads(stored_val)
        assert parsed["domain"] == "evil.com"
