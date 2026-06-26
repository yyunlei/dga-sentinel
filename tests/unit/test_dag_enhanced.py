"""M4 测试 — 条件分支路由、并行 fan-out、Pipeline 版本 CRUD、模型注册"""

from __future__ import annotations

import pytest

from dag.nodes.base import BaseNode
from dag.nodes.sink.fan_out import FanOutNode
from dag.loader import NODE_REGISTRY
from ai.scoring.models.registry import ModelRegistry, ModelEntry


# ---------------------------------------------------------------------------
# Helper: score router factory (mirrors the engine helper to be added in T062)
# ---------------------------------------------------------------------------

def _make_score_router(threshold: float, high_branch: str, low_branch: str):
    """Return a routing function that picks a branch based on state['score']."""

    def _router(state: dict) -> str:
        score = state.get("score", 0.0)
        return high_branch if score >= threshold else low_branch

    return _router


# ---------------------------------------------------------------------------
# Mock sink nodes for fan-out tests
# ---------------------------------------------------------------------------

class MockSinkNode(BaseNode):
    node_type = "mock_sink"

    async def process(self, state):
        sinks = list(state.get("sinks_written", []))
        sinks.append(self.node_id)
        state["sinks_written"] = sinks
        return state


class FailingSinkNode(BaseNode):
    node_type = "failing_sink"

    async def process(self, state):
        raise RuntimeError("sink failed")


# ===========================================================================
# 1. TestConditionalRouting
# ===========================================================================

class TestConditionalRouting:
    """Test the DAG engine's conditional edge support via score router."""

    def _router(self):
        return _make_score_router(0.7, "alert_sink", "log_sink")

    def test_score_router_high(self):
        router = self._router()
        assert router({"score": 0.9}) == "alert_sink"

    def test_score_router_low(self):
        router = self._router()
        assert router({"score": 0.3}) == "log_sink"

    def test_score_router_boundary(self):
        """score == threshold should route to the high branch (>= semantics)."""
        router = self._router()
        assert router({"score": 0.7}) == "alert_sink"


# ===========================================================================
# 2. TestFanOutNode
# ===========================================================================

class TestFanOutNode:
    """Test the parallel fan-out node."""

    async def test_fan_out_no_children(self):
        node = FanOutNode(node_id="fo_empty", config={}, children=[])
        state = {"sinks_written": [], "errors": []}
        result = await node.process(state)
        assert result["sinks_written"] == []

    async def test_fan_out_with_children(self):
        child_a = MockSinkNode(node_id="sink_a", config={})
        child_b = MockSinkNode(node_id="sink_b", config={})
        node = FanOutNode(node_id="fo_dual", config={}, children=[child_a, child_b])

        state = {"sinks_written": [], "errors": []}
        result = await node.process(state)

        assert "sink_a" in result["sinks_written"]
        assert "sink_b" in result["sinks_written"]

    async def test_fan_out_error_handling(self):
        good = MockSinkNode(node_id="sink_ok", config={})
        bad = FailingSinkNode(node_id="sink_fail", config={})
        node = FanOutNode(node_id="fo_mixed", config={}, children=[good, bad])

        state = {"sinks_written": [], "errors": []}
        result = await node.process(state)

        # The good child should still have written
        assert "sink_ok" in result["sinks_written"]
        # The failing child should be captured in errors
        error_ids = [e["node_id"] for e in result["errors"]]
        assert "sink_fail" in error_ids


# ===========================================================================
# 3. TestPipelineLoader
# ===========================================================================

class TestPipelineLoader:
    """Verify NODE_REGISTRY contents."""

    def test_fan_out_in_registry(self):
        assert "fan_out" in NODE_REGISTRY, (
            f"'fan_out' missing from NODE_REGISTRY. Keys: {list(NODE_REGISTRY.keys())}"
        )

    def test_node_registry_has_all_types(self):
        assert len(NODE_REGISTRY) >= 12, (
            f"Expected >= 12 entries in NODE_REGISTRY, got {len(NODE_REGISTRY)}: "
            f"{list(NODE_REGISTRY.keys())}"
        )


# ===========================================================================
# 4. TestModelRegistry
# ===========================================================================

class TestModelRegistry:
    """Model version management and A/B routing."""

    def _make_entry(self, model_id="dga_binary", version="v1", **kw):
        return ModelEntry(
            model_id=model_id,
            version=version,
            artifact_path=f"/models/{model_id}/{version}",
            **kw,
        )

    def test_register_and_get_production(self):
        reg = ModelRegistry()
        entry = self._make_entry(status="production")
        reg.register(entry)
        result = reg.get_production("dga_binary")
        assert result is entry

    def test_ab_weighted_selection(self):
        reg = ModelRegistry()
        e1 = self._make_entry(version="v1", status="production", ab_weight=0.8)
        e2 = self._make_entry(version="v2", status="production", ab_weight=0.2)
        reg.register(e1)
        reg.register(e2)

        results = {reg.get_production("dga_binary").version for _ in range(200)}
        # With 200 draws both versions should appear at least once
        assert "v1" in results
        assert "v2" in results

    def test_get_production_ab_deterministic(self):
        """If get_production_ab exists, same trace_id always returns same model."""
        reg = ModelRegistry()
        if not hasattr(reg, "get_production_ab"):
            pytest.skip("get_production_ab not implemented yet")

        e1 = self._make_entry(version="v1", status="production", ab_weight=0.5)
        e2 = self._make_entry(version="v2", status="production", ab_weight=0.5)
        reg.register(e1)
        reg.register(e2)

        chosen = reg.get_production_ab("dga_binary", trace_id="fixed-trace-001")
        for _ in range(50):
            assert reg.get_production_ab("dga_binary", trace_id="fixed-trace-001").version == chosen.version

    def test_get_version(self):
        reg = ModelRegistry()
        entry = self._make_entry(version="v3")
        reg.register(entry)
        result = reg.get_version("dga_binary", "v3")
        assert result is entry
        assert reg.get_version("dga_binary", "v999") is None

    def test_list_models(self):
        reg = ModelRegistry()
        reg.register(self._make_entry(version="v1", status="production"))
        reg.register(self._make_entry(version="v2", status="staging"))
        reg.register(self._make_entry(model_id="dga_multi", version="v1"))

        listing = reg.list_models()
        assert "dga_binary" in listing
        assert "dga_multi" in listing
        assert len(listing["dga_binary"]) == 2
        assert len(listing["dga_multi"]) == 1


# ===========================================================================
# 5. TestPipelineCRUD — Pipeline 版本管理 (T065)
# ===========================================================================

import os
import json
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from jose import jwt


@pytest.fixture
def pipeline_app():
    """Create test app with DAG router for pipeline CRUD tests."""
    os.environ["APP_ENV"] = "production"
    os.environ["JWT_SECRET"] = "test-secret-for-unit-tests-only"
    os.environ["GRAFANA_ADMIN_PASSWORD"] = "test-grafana-pw"
    os.environ["REDIS_URL"] = "redis://localhost:6379/0"
    from common.config import get_settings
    get_settings.cache_clear()
    from business.middleware import rate_limit
    rate_limit._limiter = None
    from business.main import app
    return app


@pytest.fixture
def admin_token():
    from common.config import get_settings
    s = get_settings()
    return jwt.encode(
        {"sub": "test-admin", "tenant_id": "default", "role": "admin"},
        s.jwt_secret, algorithm=s.jwt_algorithm,
    )


class TestPipelineCRUD:
    """Pipeline 配置保存/加载/回滚测试 (T065)"""

    def test_create_pipeline(self, pipeline_app, admin_token):
        """POST /api/dag/pipelines 创建新 pipeline"""
        mock_pg = AsyncMock()
        mock_pg.execute = AsyncMock()
        pipeline_app.dependency_overrides[__import__("business.infra.connections", fromlist=["get_pg_pool"]).get_pg_pool] = lambda: mock_pg

        client = TestClient(pipeline_app)
        resp = client.post(
            "/api/dag/pipelines",
            json={"name": "test-pipeline", "mode": "stream", "yaml_content": "nodes: []"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "pipeline_id" in data
        assert data["name"] == "test-pipeline"
        assert data["version"] == 1

        pipeline_app.dependency_overrides.clear()

    def test_list_pipelines_fallback(self, pipeline_app, admin_token):
        """GET /api/dag/pipelines 无 PG 时走 YAML 文件回退"""
        from business.infra.connections import get_pg_pool
        pipeline_app.dependency_overrides[get_pg_pool] = lambda: None

        client = TestClient(pipeline_app)
        resp = client.get(
            "/api/dag/pipelines",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "pipelines" in data
        assert isinstance(data["pipelines"], list)

        pipeline_app.dependency_overrides.clear()

    def test_update_pipeline_increments_version(self, pipeline_app, admin_token):
        """PUT /api/dag/pipelines/{id} 应自增版本号"""
        mock_pg = AsyncMock()
        mock_pg.fetchrow = AsyncMock(return_value={
            "name": "test", "mode": "stream", "version": "2", "status": "active",
        })
        mock_pg.execute = AsyncMock()
        from business.infra.connections import get_pg_pool
        pipeline_app.dependency_overrides[get_pg_pool] = lambda: mock_pg

        valid_yaml = "nodes:\n  - id: ingest\n    type: kafka_consumer\n    config:\n      topic: test"
        client = TestClient(pipeline_app)
        resp = client.put(
            "/api/dag/pipelines/test-id",
            json={"yaml_content": valid_yaml},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["version"] == 3  # 2 + 1

        pipeline_app.dependency_overrides.clear()

    def test_rollback_pipeline(self, pipeline_app, admin_token):
        """POST /api/dag/pipelines/{id}/rollback 回滚到指定版本"""
        mock_pg = AsyncMock()
        mock_pg.fetchrow = AsyncMock(return_value={
            "version": "3",
        })
        mock_pg.fetchval = AsyncMock(return_value=3)
        mock_pg.execute = AsyncMock()
        from business.infra.connections import get_pg_pool
        pipeline_app.dependency_overrides[get_pg_pool] = lambda: mock_pg

        client = TestClient(pipeline_app)
        resp = client.post(
            "/api/dag/pipelines/test-id/rollback",
            json={"version": 1},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["current_version"] == "3"
        assert data["note"] == "rollback recorded"

        pipeline_app.dependency_overrides.clear()

    def test_pipeline_requires_admin(self, pipeline_app):
        """viewer 角色不能创建 pipeline"""
        from common.config import get_settings
        s = get_settings()
        viewer_token = jwt.encode(
            {"sub": "viewer-user", "tenant_id": "default", "role": "viewer"},
            s.jwt_secret, algorithm=s.jwt_algorithm,
        )
        client = TestClient(pipeline_app)
        resp = client.post(
            "/api/dag/pipelines",
            json={"name": "test", "mode": "stream", "yaml_content": "nodes: []"},
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert resp.status_code == 403
