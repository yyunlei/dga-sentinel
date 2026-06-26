"""
模型管理数据层 — 封装所有 model_versions + audit_log PG 操作。
业务规则不在此处。构造注入 pg pool。
"""
from __future__ import annotations

import json

import asyncpg


class ModelRepo:
    def __init__(self, pg: asyncpg.Pool | None) -> None:
        self._pg = pg

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    async def list_models(self) -> list[asyncpg.Record]:
        """列出所有模型版本，按 model_id, version 排序。"""
        return await self._pg.fetch(
            "SELECT model_id, version, status, ab_weight, metrics, created_at, deployed_at "
            "FROM model_versions ORDER BY model_id, version"
        )

    async def get_model_history(self, model_id: str, limit: int = 50) -> list[asyncpg.Record]:
        """获取模型操作历史（来自 audit_log）。"""
        return await self._pg.fetch(
            "SELECT id, user_id, action, detail, created_at FROM audit_log "
            "WHERE resource=$1 AND action LIKE 'model_%' ORDER BY created_at DESC LIMIT $2",
            model_id, limit,
        )

    async def get_model_versions(self, model_id: str) -> list[asyncpg.Record]:
        """列出模型所有版本（供回滚选择）。"""
        return await self._pg.fetch(
            "SELECT version, status, created_at, deployed_at FROM model_versions "
            "WHERE model_id=$1 ORDER BY created_at DESC",
            model_id,
        )

    # ------------------------------------------------------------------
    # AB 测试配置
    # ------------------------------------------------------------------

    async def configure_ab_test_by_version(
        self, model_a: str, model_b: str, weight_a: float
    ) -> None:
        """按版本号设置 A/B 权重（前端格式：model_a/model_b/weight_a）。"""
        async with self._pg.acquire() as conn:
            await conn.execute(
                "UPDATE model_versions SET ab_weight=$1 WHERE version=$2",
                weight_a, model_a,
            )
            await conn.execute(
                "UPDATE model_versions SET ab_weight=$1 WHERE version=$2",
                1.0 - weight_a, model_b,
            )

    async def configure_ab_test_by_model(
        self, model_id: str, versions: dict[str, float]
    ) -> None:
        """按 model_id + version 批量设置 A/B 权重。"""
        async with self._pg.acquire() as conn:
            for version, weight in versions.items():
                await conn.execute(
                    "UPDATE model_versions SET ab_weight=$1 WHERE model_id=$2 AND version=$3",
                    weight, model_id, version,
                )

    # ------------------------------------------------------------------
    # 状态变更
    # ------------------------------------------------------------------

    async def rollback_model(self, model_id: str, to_version: str) -> None:
        """回滚：将当前 production 归档，将目标版本设为 production。"""
        async with self._pg.acquire() as conn:
            await conn.execute(
                "UPDATE model_versions SET status='archived' WHERE model_id=$1 AND status='production'",
                model_id,
            )
            await conn.execute(
                "UPDATE model_versions SET status='production', deployed_at=NOW() WHERE model_id=$1 AND version=$2",
                model_id, to_version,
            )

    async def deploy_model(self, model_id: str, to_version: str) -> None:
        """上线：将当前 production 降为 staging，将目标版本设为 production。"""
        async with self._pg.acquire() as conn:
            await conn.execute(
                "UPDATE model_versions SET status='staging' WHERE model_id=$1 AND status='production'",
                model_id,
            )
            await conn.execute(
                "UPDATE model_versions SET status='production', deployed_at=NOW() WHERE model_id=$1 AND version=$2",
                model_id, to_version,
            )

    async def offline_model(self, model_id: str) -> None:
        """下线：将当前 production 改为 staging，清空 deployed_at。"""
        async with self._pg.acquire() as conn:
            await conn.execute(
                "UPDATE model_versions SET status='staging', deployed_at=NULL WHERE model_id=$1 AND status='production'",
                model_id,
            )

    # ------------------------------------------------------------------
    # 审计日志
    # ------------------------------------------------------------------

    async def log_model_op(self, model_id: str, action: str, detail: dict) -> None:
        """写入 audit_log，失败时静默（保持原行为）。"""
        if not self._pg:
            return
        try:
            await self._pg.execute(
                "INSERT INTO audit_log (user_id, action, resource, detail) VALUES ($1, $2, $3, $4::jsonb)",
                "admin", action, model_id, json.dumps(detail),
            )
        except Exception:
            pass
