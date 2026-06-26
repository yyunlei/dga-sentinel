"""
T090 集成测试 — 自然语言 → SQL → 执行 → 解读
验证:
  - Text2SQLEngine 初始化与表白名单
  - SQL 校验 (SELECT 允许, DROP/DELETE/INSERT 拒绝)
  - IntentRouter 意图分类
  - /api/query 端点结构
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from jose import jwt

from common.config import get_settings


# ── Fixtures ──────────────────────────────────────────────

@pytest.fixture
def settings():
    return get_settings()


@pytest.fixture
def valid_token(settings):
    payload = {"sub": "test-user", "tenant_id": "default", "role": "admin"}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


@pytest.fixture
def auth_headers(valid_token):
    return {"Authorization": f"Bearer {valid_token}"}


@pytest.fixture
def app():
    os.environ["APP_ENV"] = "production"
    os.environ["REDIS_URL"] = "redis://localhost:6379/0"
    from common.config import get_settings
    get_settings.cache_clear()
    from business.middleware import rate_limit
    rate_limit._limiter = None
    from business.main import app
    yield app
    os.environ["APP_ENV"] = "development"
    get_settings.cache_clear()
    rate_limit._limiter = None


# ── Text2SQLEngine Tests ──────────────────────────────────

class TestText2SQLEngine:

    def test_engine_initialization(self):
        from ai.agents.text2sql.engine import Text2SQLEngine
        engine = Text2SQLEngine(db_type="starrocks")
        assert engine.db_type == "starrocks"
        assert "dga_events" in engine.allowed_tables
        assert "alert_summary" in engine.allowed_tables

    def test_validate_select_allowed(self):
        from ai.agents.text2sql.engine import Text2SQLEngine
        engine = Text2SQLEngine(db_type="starrocks")
        result = engine._validate_sql("SELECT * FROM dga_events LIMIT 10")
        assert result is None  # no error

    def test_validate_drop_rejected(self):
        from ai.agents.text2sql.engine import Text2SQLEngine
        engine = Text2SQLEngine(db_type="starrocks")
        result = engine._validate_sql("DROP TABLE dga_events")
        assert result is not None
        assert "SELECT" in result or "Forbidden" in result

    def test_validate_delete_rejected(self):
        from ai.agents.text2sql.engine import Text2SQLEngine
        engine = Text2SQLEngine(db_type="starrocks")
        result = engine._validate_sql("DELETE FROM dga_events WHERE 1=1")
        assert result is not None

    def test_validate_insert_rejected(self):
        from ai.agents.text2sql.engine import Text2SQLEngine
        engine = Text2SQLEngine(db_type="starrocks")
        result = engine._validate_sql("INSERT INTO dga_events VALUES ('a','b')")
        assert result is not None

    def test_validate_unknown_table_rejected(self):
        from ai.agents.text2sql.engine import Text2SQLEngine
        engine = Text2SQLEngine(db_type="starrocks")
        result = engine._validate_sql("SELECT * FROM secret_table")
        assert result is not None
        assert "unknown" in result.lower()


# ── Schema Registry Tests ─────────────────────────────────

class TestSchemaRegistry:

    def test_allowed_tables_starrocks(self):
        from ai.agents.text2sql.schema_registry import get_allowed_tables
        tables = get_allowed_tables("starrocks")
        assert "dga_events" in tables
        assert "alert_summary" in tables

    def test_schema_context_contains_ddl(self):
        from ai.agents.text2sql.schema_registry import get_schema_context
        ctx = get_schema_context("starrocks")
        assert "CREATE TABLE" in ctx
        assert "dga_events" in ctx


# ── IntentRouter Tests ────────────────────────────────────

class TestIntentRouter:

    def test_classify_query_intent(self):
        from ai.agents.intent_router import IntentRouter
        router = IntentRouter()
        intent = router.classify_intent("查询过去24小时告警")
        assert intent == "query"

    def test_classify_knowledge_intent(self):
        from ai.agents.intent_router import IntentRouter
        router = IntentRouter()
        intent = router.classify_intent("conficker家族特征")
        assert intent == "knowledge"

    def test_classify_analyze_intent(self):
        from ai.agents.intent_router import IntentRouter
        router = IntentRouter()
        intent = router.classify_intent("分析这个告警事件")
        assert intent == "analyze"

    def test_classify_default_fallback(self):
        from ai.agents.intent_router import IntentRouter
        router = IntentRouter()
        intent = router.classify_intent("hello world random text")
        assert intent == "query"  # default fallback


# ── Query Endpoint Tests ─────────────────────────────────

class TestQueryEndpoint:

    @patch("agent_layer.text2sql.engine.Text2SQLEngine")
    def test_query_endpoint_returns_structure(
        self, mock_engine_cls, app, auth_headers,
    ):
        mock_engine = MagicMock()
        mock_engine.query = AsyncMock(return_value={
            "sql": "SELECT * FROM dga_events LIMIT 20",
            "data": [{"domain": "evil.com", "score": 0.95}],
            "explanation": "查询返回 1 条结果",
        })
        mock_engine_cls.return_value = mock_engine

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/api/query",
            json={"question": "查询最近的告警", "db_type": "starrocks"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "sql" in data
        assert "data" in data
        assert "explanation" in data
