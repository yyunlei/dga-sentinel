"""ModelRegistry 单元测试"""

import pytest
from scoring_service.models.registry import ModelRegistry, ModelEntry


class TestModelRegistry:
    def test_register_and_list(self):
        reg = ModelRegistry()
        reg.register(ModelEntry(model_id="test", version="v1", artifact_path="/tmp/m1", status="production"))
        models = reg.list_models()
        assert "test" in models
        assert len(models["test"]) == 1

    def test_get_production(self):
        reg = ModelRegistry()
        reg.register(ModelEntry(model_id="test", version="v1", artifact_path="/tmp/m1", status="staging"))
        reg.register(ModelEntry(model_id="test", version="v2", artifact_path="/tmp/m2", status="production"))
        entry = reg.get_production("test")
        assert entry is not None
        assert entry.version == "v2"

    def test_get_production_none(self):
        reg = ModelRegistry()
        assert reg.get_production("nonexistent") is None

    def test_get_version(self):
        reg = ModelRegistry()
        reg.register(ModelEntry(model_id="test", version="v1", artifact_path="/tmp/m1"))
        entry = reg.get_version("test", "v1")
        assert entry is not None
        assert entry.version == "v1"

    def test_ab_weight_selection(self):
        reg = ModelRegistry()
        reg.register(ModelEntry(model_id="test", version="v1", artifact_path="/tmp/m1", status="production", ab_weight=0.8))
        reg.register(ModelEntry(model_id="test", version="v2", artifact_path="/tmp/m2", status="production", ab_weight=0.2))
        # Just verify it returns one of the two
        entry = reg.get_production("test")
        assert entry is not None
        assert entry.version in ("v1", "v2")
