"""M3 测试 — Text2SQL SQL 安全校验"""
from __future__ import annotations

import pytest

from ai.agents.text2sql.engine import Text2SQLEngine, FORBIDDEN_KEYWORDS
from ai.agents.text2sql.schema_registry import (
    get_schema_context,
    get_allowed_tables,
    SCHEMA_REGISTRY,
)


# ------------------------------------------------------------------ #
#  T1: SQL 校验
# ------------------------------------------------------------------ #

class TestText2SQLValidation:
    """_validate_sql 白名单 + 黑名单校验。"""

    def setup_method(self):
        self.engine = Text2SQLEngine("starrocks")

    def test_select_allowed(self):
        result = self.engine._validate_sql("SELECT * FROM dga_events")
        assert result is None

    def test_drop_rejected(self):
        result = self.engine._validate_sql("DROP TABLE dga_events")
        assert result is not None and isinstance(result, str)

    def test_delete_rejected(self):
        result = self.engine._validate_sql("DELETE FROM dga_events")
        assert result is not None and isinstance(result, str)

    def test_insert_rejected(self):
        result = self.engine._validate_sql(
            "INSERT INTO dga_events VALUES ('a','b','c',0.5,'x',true,now(),'v1')"
        )
        assert result is not None and isinstance(result, str)

    def test_unknown_table_rejected(self):
        result = self.engine._validate_sql("SELECT * FROM secret_table")
        assert result is not None and isinstance(result, str)

    def test_forbidden_keywords_complete(self):
        expected = {
            "DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "CREATE",
            "TRUNCATE", "GRANT", "REVOKE", "EXEC", "EXECUTE",
            "INTO OUTFILE", "LOAD DATA",
        }
        assert FORBIDDEN_KEYWORDS == expected


# ------------------------------------------------------------------ #
#  T2: Schema Registry
# ------------------------------------------------------------------ #

class TestSchemaRegistry:
    """表白名单与 DDL 上下文。"""

    def test_starrocks_tables(self):
        tables = get_allowed_tables("starrocks")
        assert "dga_events" in tables

    def test_postgres_tables(self):
        tables = get_allowed_tables("postgres")
        assert "model_versions" in tables
        assert "feedback" in tables

    def test_schema_context_not_empty(self):
        ctx = get_schema_context("starrocks")
        assert len(ctx) > 0
        assert "CREATE TABLE" in ctx

    def test_unknown_db_returns_empty(self):
        tables = get_allowed_tables("unknown")
        assert tables == set()


# ------------------------------------------------------------------ #
#  T3: Text2SQLEngine
# ------------------------------------------------------------------ #

class TestText2SQLEngine:
    """Engine 初始化与 fallback SQL 生成。"""

    def test_engine_init(self):
        engine = Text2SQLEngine("starrocks")
        assert engine.db_type == "starrocks"
        assert "dga_events" in engine.allowed_tables

    def test_fallback_sql_alerts(self):
        engine = Text2SQLEngine("starrocks")
        sql = engine._fallback_sql("告警趋势统计")
        assert "alert_summary" in sql

    def test_fallback_sql_model(self):
        engine = Text2SQLEngine("starrocks")
        sql = engine._fallback_sql("模型信息")
        assert "model_versions" in sql

    def test_fallback_sql_default(self):
        engine = Text2SQLEngine("starrocks")
        sql = engine._fallback_sql("random")
        assert "dga_events" in sql
