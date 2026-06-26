"""
模型管理业务逻辑。
不依赖 FastAPI，只依赖 ModelRepo。可独立单测。
"""
from __future__ import annotations

import json


class ModelService:
    """模型管理业务编排：状态转换、AB 配置校验等，不做 HTTP。"""

    def __init__(self, repo) -> None:
        self._repo = repo

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    async def list_models(self) -> list[dict]:
        """返回所有模型版本的 dict 列表。"""
        rows = await self._repo.list_models()
        return [
            {
                "model_id": r["model_id"],
                "version": r["version"],
                "status": r["status"],
                "ab_weight": float(r["ab_weight"]),
                "metrics": (
                    json.loads(r["metrics"])
                    if isinstance(r.get("metrics"), str)
                    else (dict(r["metrics"]) if r.get("metrics") else {})
                ),
                "created_at": str(r["created_at"]) if r.get("created_at") else None,
                "deployed_at": str(r["deployed_at"]) if r.get("deployed_at") else None,
            }
            for r in rows
        ]

    async def get_model_history(self, model_id: str, limit: int = 50) -> list[dict]:
        """返回模型操作历史 dict 列表。"""
        rows = await self._repo.get_model_history(model_id, limit)
        return [
            {
                "id": r["id"],
                "user_id": r["user_id"],
                "action": r["action"],
                "detail": (
                    json.loads(r["detail"])
                    if isinstance(r.get("detail"), str)
                    else (dict(r["detail"]) if r.get("detail") else {})
                ),
                "created_at": str(r["created_at"]),
            }
            for r in rows
        ]

    async def get_model_versions(self, model_id: str) -> list[dict]:
        """返回模型版本列表 dict。"""
        rows = await self._repo.get_model_versions(model_id)
        return [
            {
                "version": r["version"],
                "status": r["status"],
                "created_at": str(r["created_at"]) if r.get("created_at") else None,
                "deployed_at": str(r["deployed_at"]) if r.get("deployed_at") else None,
            }
            for r in rows
        ]

    # ------------------------------------------------------------------
    # AB 测试配置
    # ------------------------------------------------------------------

    async def configure_ab_test(
        self,
        *,
        model_id: str | None = None,
        versions: dict[str, float] | None = None,
        model_a: str | None = None,
        model_b: str | None = None,
        weight_a: float | None = None,
    ) -> dict:
        """配置 A/B 测试，支持前端格式（model_a/model_b/weight_a）和传统格式（model_id/versions）。"""
        if model_a is not None and model_b is not None and weight_a is not None:
            await self._repo.configure_ab_test_by_version(model_a, model_b, weight_a)
            return {"ok": True, "status": "configured"}
        if model_id and versions:
            await self._repo.configure_ab_test_by_model(model_id, versions)
            return {"ok": True, "status": "configured"}
        return {"ok": True, "status": "configured", "note": "no config applied"}

    # ------------------------------------------------------------------
    # 状态变更
    # ------------------------------------------------------------------

    async def rollback_model(self, model_id: str, to_version: str | None) -> dict:
        """回滚到指定版本。to_version 为空时返回错误 dict（不触碰 DB）。"""
        if not to_version:
            return {"ok": False, "error": "请提供 version（回滚目标版本）"}
        await self._repo.rollback_model(model_id, to_version)
        await self._repo.log_model_op(model_id, "model_rollback", {"to_version": to_version})
        return {"ok": True, "model_id": model_id, "rolled_back_to": to_version}

    async def deploy_model(self, model_id: str, to_version: str | None) -> dict:
        """将指定版本上线为 production。to_version 为空时返回错误 dict。"""
        if not to_version:
            return {"ok": False, "error": "请提供 version（要上线的版本）"}
        await self._repo.deploy_model(model_id, to_version)
        await self._repo.log_model_op(model_id, "model_deploy", {"version": to_version})
        return {"ok": True, "model_id": model_id, "deployed_version": to_version}

    async def offline_model(self, model_id: str) -> dict:
        """将当前 production 版本下线，改为 staging。"""
        await self._repo.offline_model(model_id)
        await self._repo.log_model_op(model_id, "model_offline", {"model_id": model_id})
        return {"ok": True, "model_id": model_id, "status": "staging"}
