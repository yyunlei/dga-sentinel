"""
模型注册表 — 管理模型版本、A/B 测试路由
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field
from pathlib import Path

import asyncpg

from shared.config import get_settings
from shared.observability import get_logger

logger = get_logger(__name__)


@dataclass
class ModelEntry:
    model_id: str
    version: str
    artifact_path: str
    status: str = "staging"  # staging / production / archived
    ab_weight: float = 1.0
    instance: object = None  # 加载后的模型实例


class ModelRegistry:
    """
    模型注册表：管理多版本模型，支持 A/B 路由
    """

    def __init__(self):
        self._models: dict[str, list[ModelEntry]] = {}

    def register(self, entry: ModelEntry) -> None:
        """注册模型版本"""
        if entry.model_id not in self._models:
            self._models[entry.model_id] = []
        self._models[entry.model_id].append(entry)
        logger.info("model_registered", model_id=entry.model_id, version=entry.version)

    def get_production(self, model_id: str) -> ModelEntry | None:
        """获取 production 状态的模型（支持 A/B 加权选择）"""
        entries = self._models.get(model_id, [])
        prod_entries = [e for e in entries if e.status == "production"]
        if not prod_entries:
            return None
        if len(prod_entries) == 1:
            return prod_entries[0]

        # A/B 加权随机选择
        weights = [e.ab_weight for e in prod_entries]
        total = sum(weights)
        if total == 0:
            return prod_entries[0]
        return random.choices(prod_entries, weights=weights, k=1)[0]

    def get_version(self, model_id: str, version: str) -> ModelEntry | None:
        """获取指定版本"""
        entries = self._models.get(model_id, [])
        for e in entries:
            if e.version == version:
                return e
        return None

    def list_models(self) -> dict[str, list[dict]]:
        """列出所有模型"""
        result = {}
        for model_id, entries in self._models.items():
            result[model_id] = [
                {"version": e.version, "status": e.status, "ab_weight": e.ab_weight}
                for e in entries
            ]
        return result

    # ---- T066: PG persistence ----

    async def load_from_pg(self) -> None:
        """从 model_versions 表加载所有模型到内存"""
        conn: asyncpg.Connection | None = None
        try:
            settings = get_settings()
            conn = await asyncpg.connect(settings.pg_dsn)
            rows = await conn.fetch(
                "SELECT model_id, version, status, ab_weight FROM model_versions ORDER BY id"
            )
            for row in rows:
                entry = ModelEntry(
                    model_id=row["model_id"],
                    version=row["version"],
                    artifact_path="",
                    status=row["status"] or "staging",
                )
                if row["ab_weight"] is not None:
                    entry.ab_weight = row["ab_weight"]
                if entry.model_id not in self._models:
                    self._models[entry.model_id] = []
                self._models[entry.model_id].append(entry)
            logger.info("models_loaded_from_pg", count=len(rows))
        except Exception as exc:
            logger.warning("pg_load_failed", error=str(exc))
        finally:
            if conn:
                await conn.close()

    async def save_to_pg(self, entry: ModelEntry) -> None:
        """将模型条目保存到 PG（insert or update）"""
        conn: asyncpg.Connection | None = None
        try:
            settings = get_settings()
            conn = await asyncpg.connect(settings.pg_dsn)
            # Check if exists
            existing = await conn.fetchrow(
                "SELECT id FROM model_versions WHERE model_id=$1 AND version=$2",
                entry.model_id, entry.version,
            )
            if existing:
                await conn.execute(
                    "UPDATE model_versions SET status=$1, ab_weight=$2 "
                    "WHERE model_id=$3 AND version=$4",
                    entry.status, entry.ab_weight, entry.model_id, entry.version,
                )
            else:
                await conn.execute(
                    "INSERT INTO model_versions (model_id, version, artifact_path, status, ab_weight) "
                    "VALUES ($1, $2, $3, $4, $5)",
                    entry.model_id, entry.version, entry.artifact_path or "", entry.status, entry.ab_weight,
                )
            logger.info("model_saved_to_pg", model_id=entry.model_id, version=entry.version)
        except Exception as exc:
            logger.warning("pg_save_failed", error=str(exc))
        finally:
            if conn:
                await conn.close()

    async def reload(self) -> None:
        """清空内存缓存并从 PG 重新加载"""
        self._models.clear()
        await self.load_from_pg()
        logger.info("registry_reloaded")

    async def handle_reload(self) -> dict:
        """处理 /reload 请求"""
        await self.reload()
        return {"ok": True, "models": len(self._models)}

    # ---- T067: deterministic A/B routing ----

    def get_production_ab(self, model_id: str, trace_id: str = "") -> ModelEntry | None:
        """基于 trace_id hash 的确定性 A/B 路由"""
        entries = self._models.get(model_id, [])
        prod_entries = [e for e in entries if e.status == "production"]
        if not prod_entries:
            return None
        if len(prod_entries) == 1:
            return prod_entries[0]

        if trace_id:
            # Deterministic: hash trace_id to [0, 1)
            h = hashlib.md5(trace_id.encode()).hexdigest()
            ratio = int(h[:8], 16) / 0xFFFFFFFF
            # Cumulative weight selection
            weights = [e.ab_weight for e in prod_entries]
            total = sum(weights)
            if total == 0:
                return prod_entries[0]
            cumulative = 0.0
            for entry, w in zip(prod_entries, weights):
                cumulative += w / total
                if ratio < cumulative:
                    return entry
            return prod_entries[-1]

        # Fallback: random weighted selection
        weights = [e.ab_weight for e in prod_entries]
        total = sum(weights)
        if total == 0:
            return prod_entries[0]
        return random.choices(prod_entries, weights=weights, k=1)[0]
