"""
Integration tests for alert domain aggregation API endpoints.
Tasks: T005 (GET /alerts/grouped), T014 (expand drill-down), T018 (POST /acknowledge-by-domain)

These tests mock the ES HTTP layer (httpx) to test endpoint logic
without requiring a running Elasticsearch instance.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from httpx import Response

from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app():
    """Create a FastAPI test app with auth and ES dependency bypassed."""
    from business.main import app as _app
    from business.middleware.rbac import require_analyst, require_write
    from business.repositories.pg_repo import get_es_client

    mock_es = MagicMock()
    mock_es.__bool__ = lambda self: True

    _app.dependency_overrides[require_analyst] = lambda: None
    _app.dependency_overrides[require_write] = lambda: None
    _app.dependency_overrides[get_es_client] = lambda: mock_es
    yield _app
    _app.dependency_overrides.clear()


@pytest.fixture
def app_no_es():
    """Create a FastAPI test app with ES returning None (unavailable)."""
    from business.main import app as _app
    from business.middleware.rbac import require_analyst, require_write
    from business.repositories.pg_repo import get_es_client

    _app.dependency_overrides[require_analyst] = lambda: None
    _app.dependency_overrides[require_write] = lambda: None
    _app.dependency_overrides[get_es_client] = lambda: None
    yield _app
    _app.dependency_overrides.clear()


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def client_no_es(app_no_es):
    return TestClient(app_no_es)
SAMPLE_GROUPED_ES_RESPONSE = {
    "hits": {"total": {"value": 100}, "hits": []},
    "aggregations": {
        "total_unique_domains": {"value": 2},
        "by_domain": {
            "buckets": [
                {
                    "key": "evil-domain.xyz",
                    "doc_count": 47,
                    "unique_src_ips": {
                        "buckets": [
                            {"key": "10.0.0.1", "doc_count": 20},
                            {"key": "10.0.0.2", "doc_count": 15},
                        ]
                    },
                    "src_ip_count": {"value": 2},
                    "max_severity_bucket": {
                        "buckets": [
                            {"key": "CRITICAL", "doc_count": 10},
                            {"key": "HIGH", "doc_count": 20},
                            {"key": "LOW", "doc_count": 17},
                        ]
                    },
                    "max_score": {"value": 0.97},
                    "family_top": {"buckets": [{"key": "qakbot", "doc_count": 30}]},
                    "first_seen": {"value_as_string": "2026-02-19T10:05:00Z"},
                    "last_seen": {"value_as_string": "2026-02-19T10:30:00Z"},
                    "unacknowledged_count": {"doc_count": 5},
                },
                {
                    "key": "safe-domain.com",
                    "doc_count": 3,
                    "unique_src_ips": {"buckets": [{"key": "10.0.0.3", "doc_count": 3}]},
                    "src_ip_count": {"value": 1},
                    "max_severity_bucket": {
                        "buckets": [{"key": "LOW", "doc_count": 3}]
                    },
                    "max_score": {"value": 0.45},
                    "family_top": {"buckets": []},
                    "first_seen": {"value_as_string": "2026-02-19T11:00:00Z"},
                    "last_seen": {"value_as_string": "2026-02-19T11:05:00Z"},
                    "unacknowledged_count": {"doc_count": 0},
                },
            ]
        },
    },
}

SAMPLE_EMPTY_ES_RESPONSE = {
    "hits": {"total": {"value": 0}, "hits": []},
    "aggregations": {
        "total_unique_domains": {"value": 0},
        "by_domain": {"buckets": []},
    },
}

SAMPLE_ALERTS_ES_RESPONSE = {
    "hits": {
        "total": {"value": 2},
        "hits": [
            {
                "_source": {
                    "event_id": "evt-001",
                    "domain": "evil-domain.xyz",
                    "score": 0.95,
                    "family": "qakbot",
                    "severity": "CRITICAL",
                    "timestamp": "2026-02-19T10:05:00Z",
                    "src_ip": "10.0.0.1",
                    "is_dga": True,
                    "acknowledged": False,
                    "pipeline_id": "dga-realtime-v1",
                }
            },
            {
                "_source": {
                    "event_id": "evt-002",
                    "domain": "evil-domain.xyz",
                    "score": 0.88,
                    "family": "qakbot",
                    "severity": "HIGH",
                    "timestamp": "2026-02-19T10:10:00Z",
                    "src_ip": "10.0.0.2",
                    "is_dga": True,
                    "acknowledged": False,
                    "pipeline_id": "dga-realtime-v1",
                }
            },
        ],
    }
}

SAMPLE_ACK_ES_RESPONSE = {"updated": 5}


def _mock_es_client():
    """Return a truthy MagicMock that acts as an ES client placeholder."""
    m = MagicMock()
    m.__bool__ = lambda self: True
    return m


def _make_httpx_response(data: dict, status_code: int = 200) -> Response:
    """Build an httpx.Response from a dict payload with a dummy request."""
    import httpx
    req = httpx.Request("POST", "http://localhost:9200/test")
    return Response(status_code=status_code, json=data, request=req)


# ---------------------------------------------------------------------------
# T005: GET /api/alerts/grouped tests
# ---------------------------------------------------------------------------

class TestListAlertsGrouped:
    """Integration tests for the domain-aggregated alert list endpoint."""

    @patch("business.api.alerts.get_es_client")
    @patch("httpx.AsyncClient")
    def test_default_params_returns_groups(self, mock_httpx_cls, mock_es, client):
        mock_es.return_value = _mock_es_client()
        mock_client_instance = AsyncMock()
        mock_client_instance.post.return_value = _make_httpx_response(SAMPLE_GROUPED_ES_RESPONSE)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)
        mock_httpx_cls.return_value = mock_client_instance

        resp = client.get("/api/alerts/grouped")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_domains"] == 2
        assert len(data["groups"]) == 2
        # First group
        g0 = data["groups"][0]
        assert g0["domain"] == "evil-domain.xyz"
        assert g0["alert_count"] == 47
        assert g0["max_severity"] == "CRITICAL"
        assert g0["max_score"] == 0.97
        assert g0["family"] == "qakbot"
        assert g0["all_acknowledged"] is False
        assert g0["unique_src_ip_count"] == 2
        assert "10.0.0.1" in g0["unique_src_ips"]

    @patch("business.api.alerts.get_es_client")
    @patch("httpx.AsyncClient")
    def test_empty_result(self, mock_httpx_cls, mock_es, client):
        mock_es.return_value = _mock_es_client()
        mock_client_instance = AsyncMock()
        mock_client_instance.post.return_value = _make_httpx_response(SAMPLE_EMPTY_ES_RESPONSE)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)
        mock_httpx_cls.return_value = mock_client_instance

        resp = client.get("/api/alerts/grouped")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_domains"] == 0
        assert data["groups"] == []

    @patch("business.api.alerts.get_es_client")
    @patch("httpx.AsyncClient")
    def test_size_param_passed_to_es(self, mock_httpx_cls, mock_es, client):
        mock_es.return_value = _mock_es_client()
        mock_client_instance = AsyncMock()
        mock_client_instance.post.return_value = _make_httpx_response(SAMPLE_EMPTY_ES_RESPONSE)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)
        mock_httpx_cls.return_value = mock_client_instance

        resp = client.get("/api/alerts/grouped?size=100")
        assert resp.status_code == 200
        # Verify the ES query body included size=100 in the terms agg
        call_args = mock_client_instance.post.call_args
        body = call_args.kwargs.get("json") or call_args[1].get("json")
        assert body["aggs"]["by_domain"]["terms"]["size"] == 100

    def test_size_param_max_200(self, client):
        resp = client.get("/api/alerts/grouped?size=300")
        assert resp.status_code == 422  # Validation error

    @patch("business.api.alerts.get_es_client")
    @patch("httpx.AsyncClient")
    def test_all_acknowledged_true_when_zero_unack(self, mock_httpx_cls, mock_es, client):
        mock_es.return_value = _mock_es_client()
        mock_client_instance = AsyncMock()
        mock_client_instance.post.return_value = _make_httpx_response(SAMPLE_GROUPED_ES_RESPONSE)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)
        mock_httpx_cls.return_value = mock_client_instance

        resp = client.get("/api/alerts/grouped")
        data = resp.json()
        # Second group has unacknowledged_count=0
        assert data["groups"][1]["all_acknowledged"] is True
        # First group has unacknowledged_count=5
        assert data["groups"][0]["all_acknowledged"] is False

    @patch("business.api.alerts.get_es_client")
    def test_es_unavailable_returns_503(self, mock_es, client):
        mock_es.return_value = None
        resp = client.get("/api/alerts/grouped")
        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# T014: Expand drill-down tests (uses existing GET /alerts?domain=X)
# ---------------------------------------------------------------------------

class TestExpandDrillDown:
    """Integration tests for expanding a domain group to see child alerts."""

    @patch("business.api.alerts.get_es_client")
    @patch("httpx.AsyncClient")
    def test_list_alerts_filtered_by_domain(self, mock_httpx_cls, mock_es, client):
        mock_es.return_value = _mock_es_client()
        mock_client_instance = AsyncMock()
        mock_client_instance.post.return_value = _make_httpx_response(SAMPLE_ALERTS_ES_RESPONSE)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)
        mock_httpx_cls.return_value = mock_client_instance

        resp = client.get("/api/alerts?domain=evil-domain.xyz&limit=100")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["alerts"]) == 2
        # Verify child alert fields match AlertItem schema
        alert = data["alerts"][0]
        assert "event_id" in alert
        assert "domain" in alert
        assert "score" in alert
        assert "severity" in alert
        assert "timestamp" in alert
        assert "src_ip" in alert
        assert "acknowledged" in alert

    @patch("business.api.alerts.get_es_client")
    @patch("httpx.AsyncClient")
    def test_domain_filter_passed_to_es_query(self, mock_httpx_cls, mock_es, client):
        mock_es.return_value = _mock_es_client()
        mock_client_instance = AsyncMock()
        mock_client_instance.post.return_value = _make_httpx_response(SAMPLE_ALERTS_ES_RESPONSE)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)
        mock_httpx_cls.return_value = mock_client_instance

        client.get("/api/alerts?domain=evil-domain.xyz&limit=100")
        call_args = mock_client_instance.post.call_args
        body = call_args.kwargs.get("json") or call_args[1].get("json")
        query = body["query"]
        # Should contain wildcard domain filter
        assert query["bool"]["must"][0]["wildcard"]["domain.keyword"]["value"] == "*evil-domain.xyz*"


# ---------------------------------------------------------------------------
# T018: POST /api/alerts/acknowledge-by-domain tests
# ---------------------------------------------------------------------------

class TestAcknowledgeByDomain:
    """Integration tests for batch acknowledge by domain endpoint."""

    @patch("business.api.alerts.get_es_client")
    @patch("httpx.AsyncClient")
    def test_single_domain_ack(self, mock_httpx_cls, mock_es, client):
        mock_es.return_value = _mock_es_client()
        mock_client_instance = AsyncMock()
        mock_client_instance.post.return_value = _make_httpx_response(SAMPLE_ACK_ES_RESPONSE)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)
        mock_httpx_cls.return_value = mock_client_instance

        resp = client.post(
            "/api/alerts/acknowledge-by-domain",
            json={"domains": ["evil-domain.xyz"]},
        )
        assert resp.status_code == 200
        assert resp.json()["updated"] == 5

    @patch("business.api.alerts.get_es_client")
    @patch("httpx.AsyncClient")
    def test_multi_domain_ack(self, mock_httpx_cls, mock_es, client):
        mock_es.return_value = _mock_es_client()
        mock_client_instance = AsyncMock()
        mock_client_instance.post.return_value = _make_httpx_response({"updated": 12})
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)
        mock_httpx_cls.return_value = mock_client_instance

        resp = client.post(
            "/api/alerts/acknowledge-by-domain",
            json={"domains": ["evil-domain.xyz", "bad-domain.top"]},
        )
        assert resp.status_code == 200
        assert resp.json()["updated"] == 12

    @patch("business.api.alerts.get_es_client")
    @patch("httpx.AsyncClient")
    def test_idempotent_re_ack(self, mock_httpx_cls, mock_es, client):
        mock_es.return_value = _mock_es_client()
        mock_client_instance = AsyncMock()
        mock_client_instance.post.return_value = _make_httpx_response({"updated": 0})
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)
        mock_httpx_cls.return_value = mock_client_instance

        resp = client.post(
            "/api/alerts/acknowledge-by-domain",
            json={"domains": ["already-acked.xyz"]},
        )
        assert resp.status_code == 200
        assert resp.json()["updated"] == 0

    @patch("business.api.alerts.get_es_client")
    def test_empty_domains_returns_400(self, mock_es, client):
        mock_es.return_value = _mock_es_client()
        resp = client.post(
            "/api/alerts/acknowledge-by-domain",
            json={"domains": []},
        )
        assert resp.status_code == 400

    @patch("business.api.alerts.get_es_client")
    def test_es_unavailable_returns_503(self, mock_es, client):
        mock_es.return_value = None
        resp = client.post(
            "/api/alerts/acknowledge-by-domain",
            json={"domains": ["evil.xyz"]},
        )
        assert resp.status_code == 503

    @patch("business.api.alerts.get_es_client")
    @patch("httpx.AsyncClient")
    def test_update_by_query_uses_correct_filter(self, mock_httpx_cls, mock_es, client):
        mock_es.return_value = _mock_es_client()
        mock_client_instance = AsyncMock()
        mock_client_instance.post.return_value = _make_httpx_response(SAMPLE_ACK_ES_RESPONSE)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)
        mock_httpx_cls.return_value = mock_client_instance

        client.post(
            "/api/alerts/acknowledge-by-domain",
            json={"domains": ["evil.xyz", "bad.top"]},
        )
        call_args = mock_client_instance.post.call_args
        body = call_args.kwargs.get("json") or call_args[1].get("json")
        # Verify query filters by domains AND acknowledged=false
        must = body["query"]["bool"]["must"]
        assert {"terms": {"domain.keyword": ["evil.xyz", "bad.top"]}} in must
        assert {"term": {"acknowledged": False}} in must
        # Verify script sets acknowledged=true
        assert body["script"]["source"] == "ctx._source.acknowledged = true"
