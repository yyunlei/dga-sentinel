"""
ModelService 单测：fake repo，秒级运行，无需 Docker/PG。

覆盖：
  1. list_models — 透传 repo 行，字段正确转换
  2. configure_ab_test (model_a/model_b 格式) — 调 repo.configure_ab_test_by_version
  3. configure_ab_test (model_id/versions 格式) — 调 repo.configure_ab_test_by_model
  4. configure_ab_test (无配置格式) — 不调 repo，返回 note
  5. rollback_model (无 version) — 返回错误 dict，不调 repo
  6. rollback_model (有 version) — 调 repo.rollback_model + log_model_op
  7. deploy_model — 调 repo.deploy_model + log_model_op
  8. offline_model — 调 repo.offline_model + log_model_op
"""
from __future__ import annotations

import pytest

from business.services.model_service import ModelService


# ---------------------------------------------------------------------------
# Fake repo
# ---------------------------------------------------------------------------

class FakeModelRepo:
    """记录所有调用，返回可控结果。"""

    def __init__(self) -> None:
        self.calls: dict[str, list] = {}
        self._list_models_result: list[dict] = []
        self._history_result: list[dict] = []
        self._versions_result: list[dict] = []

    def _record(self, method: str, *args) -> None:
        self.calls.setdefault(method, []).append(args)

    async def list_models(self) -> list[dict]:
        self._record("list_models")
        return self._list_models_result

    async def configure_ab_test_by_version(self, model_a: str, model_b: str, weight_a: float) -> None:
        self._record("configure_ab_test_by_version", model_a, model_b, weight_a)

    async def configure_ab_test_by_model(self, model_id: str, versions: dict) -> None:
        self._record("configure_ab_test_by_model", model_id, versions)

    async def rollback_model(self, model_id: str, to_version: str) -> None:
        self._record("rollback_model", model_id, to_version)

    async def deploy_model(self, model_id: str, to_version: str) -> None:
        self._record("deploy_model", model_id, to_version)

    async def offline_model(self, model_id: str) -> None:
        self._record("offline_model", model_id)

    async def log_model_op(self, model_id: str, action: str, detail: dict) -> None:
        self._record("log_model_op", model_id, action, detail)

    async def get_model_history(self, model_id: str, limit: int = 50) -> list[dict]:
        self._record("get_model_history", model_id, limit)
        return self._history_result

    async def get_model_versions(self, model_id: str) -> list[dict]:
        self._record("get_model_versions", model_id)
        return self._versions_result


def _make_service(repo: FakeModelRepo | None = None) -> tuple[ModelService, FakeModelRepo]:
    if repo is None:
        repo = FakeModelRepo()
    return ModelService(repo=repo), repo


# ---------------------------------------------------------------------------
# Test 1: list_models — 透传并转换字段
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_models_passes_through_and_converts():
    """list_models 应透传 repo 行，正确转换 ab_weight 为 float、metrics 默认空 dict。"""
    svc, repo = _make_service()
    repo._list_models_result = [
        {
            "model_id": "xgboost",
            "version": "v1.0",
            "status": "production",
            "ab_weight": "0.8",   # 原始可能是 Decimal 或 str
            "metrics": None,
            "created_at": None,
            "deployed_at": None,
        }
    ]

    result = await svc.list_models()

    assert len(result) == 1
    m = result[0]
    assert m["model_id"] == "xgboost"
    assert m["version"] == "v1.0"
    assert m["status"] == "production"
    assert isinstance(m["ab_weight"], float)
    assert m["ab_weight"] == 0.8
    assert m["metrics"] == {}
    assert m["created_at"] is None
    assert "list_models" in repo.calls


# ---------------------------------------------------------------------------
# Test 2: configure_ab_test — model_a/model_b 格式
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_configure_ab_test_by_version_format():
    """model_a/model_b/weight_a 格式应调用 repo.configure_ab_test_by_version。"""
    svc, repo = _make_service()

    result = await svc.configure_ab_test(
        model_a="v1.0", model_b="v2.0", weight_a=0.3
    )

    assert result == {"ok": True, "status": "configured"}
    assert "configure_ab_test_by_version" in repo.calls
    call_args = repo.calls["configure_ab_test_by_version"][0]
    assert call_args == ("v1.0", "v2.0", 0.3)
    assert "configure_ab_test_by_model" not in repo.calls


# ---------------------------------------------------------------------------
# Test 3: configure_ab_test — model_id/versions 格式
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_configure_ab_test_by_model_format():
    """model_id/versions 格式应调用 repo.configure_ab_test_by_model。"""
    svc, repo = _make_service()
    versions = {"v1.0": 0.4, "v2.0": 0.6}

    result = await svc.configure_ab_test(model_id="xgboost", versions=versions)

    assert result == {"ok": True, "status": "configured"}
    assert "configure_ab_test_by_model" in repo.calls
    call_args = repo.calls["configure_ab_test_by_model"][0]
    assert call_args == ("xgboost", versions)
    assert "configure_ab_test_by_version" not in repo.calls


# ---------------------------------------------------------------------------
# Test 4: configure_ab_test — 无有效配置
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_configure_ab_test_no_config_returns_note():
    """未提供任何有效格式时，返回 note，不调用任何 repo 方法。"""
    svc, repo = _make_service()

    result = await svc.configure_ab_test()

    assert result["ok"] is True
    assert result.get("note") == "no config applied"
    assert "configure_ab_test_by_version" not in repo.calls
    assert "configure_ab_test_by_model" not in repo.calls


# ---------------------------------------------------------------------------
# Test 5: rollback_model — 无 version
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rollback_model_no_version_returns_error():
    """to_version 为 None 时，应返回错误 dict，不调用 repo。"""
    svc, repo = _make_service()

    result = await svc.rollback_model("xgboost", None)

    assert result["ok"] is False
    assert "version" in result["error"]
    assert "rollback_model" not in repo.calls
    assert "log_model_op" not in repo.calls


# ---------------------------------------------------------------------------
# Test 6: rollback_model — 有 version
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rollback_model_with_version_calls_repo():
    """有效 to_version 应调用 repo.rollback_model 和 repo.log_model_op。"""
    svc, repo = _make_service()

    result = await svc.rollback_model("xgboost", "v1.0")

    assert result == {"ok": True, "model_id": "xgboost", "rolled_back_to": "v1.0"}
    assert "rollback_model" in repo.calls
    assert repo.calls["rollback_model"][0] == ("xgboost", "v1.0")
    assert "log_model_op" in repo.calls
    log_args = repo.calls["log_model_op"][0]
    assert log_args[0] == "xgboost"
    assert log_args[1] == "model_rollback"
    assert log_args[2] == {"to_version": "v1.0"}


# ---------------------------------------------------------------------------
# Test 7: deploy_model — 无 version
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_deploy_model_no_version_returns_error():
    """to_version 为空时，返回错误 dict，不调用 repo。"""
    svc, repo = _make_service()

    result = await svc.deploy_model("xgboost", "")

    assert result["ok"] is False
    assert "deploy_model" not in repo.calls


# ---------------------------------------------------------------------------
# Test 8: deploy_model — 有 version
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_deploy_model_with_version_calls_repo():
    """有效 to_version 应调用 repo.deploy_model 和 repo.log_model_op。"""
    svc, repo = _make_service()

    result = await svc.deploy_model("xgboost", "v2.0")

    assert result == {"ok": True, "model_id": "xgboost", "deployed_version": "v2.0"}
    assert "deploy_model" in repo.calls
    assert repo.calls["deploy_model"][0] == ("xgboost", "v2.0")
    log_args = repo.calls["log_model_op"][0]
    assert log_args[1] == "model_deploy"
    assert log_args[2] == {"version": "v2.0"}


# ---------------------------------------------------------------------------
# Test 9: offline_model
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_offline_model_calls_repo():
    """offline_model 应调用 repo.offline_model 和 repo.log_model_op。"""
    svc, repo = _make_service()

    result = await svc.offline_model("xgboost")

    assert result == {"ok": True, "model_id": "xgboost", "status": "staging"}
    assert "offline_model" in repo.calls
    assert repo.calls["offline_model"][0] == ("xgboost",)
    log_args = repo.calls["log_model_op"][0]
    assert log_args[1] == "model_offline"
