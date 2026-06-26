"""
Pipeline 数据层 — 封装 pipeline_configs、pipeline_nodes、pipeline_edges、
pipeline_operations、replay_jobs、node_configs 的所有 PG 查询/更新，
以及 Redis/ES 操作和文件系统 YAML 读取。
业务规则不在此处。构造注入 pg pool + redis + es。
"""
from __future__ import annotations

import json
from pathlib import Path

import asyncpg
import yaml


class PipelineRepo:
    def __init__(
        self,
        pg: asyncpg.Pool | None = None,
        redis=None,
        es=None,
    ) -> None:
        self._pg = pg
        self._redis = redis
        self._es = es

    def has_pg(self) -> bool:
        """PG 连接池是否可用。"""
        return self._pg is not None

    # ------------------------------------------------------------------
    # Pipeline 查询
    # ------------------------------------------------------------------

    async def list_pipelines(self) -> list[asyncpg.Record] | None:
        """列出所有 pipeline；PG 不可用时返回 None（供调用方 fallback）。"""
        if not self._pg:
            return None
        return await self._pg.fetch(
            "SELECT pipeline_id, name, mode, status, version, created_at "
            "FROM pipeline_configs ORDER BY created_at DESC"
        )

    async def get_pipeline(self, pipeline_id: str) -> asyncpg.Record | None:
        """获取 pipeline 全量字段；不存在或 PG 不可用时返回 None。"""
        if not self._pg:
            return None
        return await self._pg.fetchrow(
            "SELECT * FROM pipeline_configs WHERE pipeline_id=$1",
            pipeline_id,
        )

    async def get_pipeline_meta(self, pipeline_id: str) -> asyncpg.Record | None:
        """获取 pipeline 部分字段（name, mode, version, status）。"""
        if not self._pg:
            return None
        return await self._pg.fetchrow(
            "SELECT name, mode, version, status FROM pipeline_configs WHERE pipeline_id=$1",
            pipeline_id,
        )

    async def get_pipeline_version(self, pipeline_id: str) -> asyncpg.Record | None:
        """仅获取 version 字段。"""
        if not self._pg:
            return None
        return await self._pg.fetchrow(
            "SELECT version FROM pipeline_configs WHERE pipeline_id=$1",
            pipeline_id,
        )

    async def count_pipeline_statuses(self) -> list[asyncpg.Record]:
        """统计各 pipeline 的 status；PG 不可用或异常时返回空列表。"""
        if not self._pg:
            return []
        try:
            return await self._pg.fetch(
                "SELECT pipeline_id, name, status FROM pipeline_configs"
            )
        except Exception:
            return []

    # ------------------------------------------------------------------
    # Pipeline 写入
    # ------------------------------------------------------------------

    async def create_pipeline(
        self,
        pipeline_id: str,
        name: str,
        mode: str,
        yaml_content: str,
        status: str,
        version: str,
    ) -> None:
        await self._pg.execute(
            "INSERT INTO pipeline_configs (pipeline_id, name, mode, yaml_content, status, version, created_at) "
            "VALUES ($1, $2, $3, $4, $5, $6, NOW())",
            pipeline_id, name, mode, yaml_content, status, version,
        )

    async def delete_pipeline(self, pipeline_id: str) -> str:
        """删除 pipeline，返回 execute 结果字符串（如 'DELETE 1'）。"""
        return await self._pg.execute(
            "DELETE FROM pipeline_configs WHERE pipeline_id=$1",
            pipeline_id,
        )

    async def update_pipeline(
        self,
        pipeline_id: str,
        name: str,
        mode: str,
        yaml_content: str,
        version: str,
    ) -> None:
        await self._pg.execute(
            "UPDATE pipeline_configs SET name=$1, mode=$2, yaml_content=$3, version=$4, updated_at=NOW() "
            "WHERE pipeline_id=$5",
            name, mode, yaml_content, version, pipeline_id,
        )

    async def set_pipeline_status(self, pipeline_id: str, status: str) -> None:
        """更新 pipeline 状态；PG 不可用或异常时静默忽略。"""
        if not self._pg:
            return
        try:
            await self._pg.execute(
                "UPDATE pipeline_configs SET status=$1 WHERE pipeline_id=$2",
                status, pipeline_id,
            )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 操作历史
    # ------------------------------------------------------------------

    async def record_operation(
        self,
        pipeline_id: str,
        operation: str,
        operator: str = "system",
        status: str = "success",
        detail: dict | None = None,
    ) -> None:
        """写入 pipeline_operations；PG 不可用或异常时静默忽略。"""
        if not self._pg:
            return
        try:
            await self._pg.execute(
                "INSERT INTO pipeline_operations (pipeline_id, operation, operator, status, detail) "
                "VALUES ($1, $2, $3, $4, $5::jsonb)",
                pipeline_id, operation, operator, status, json.dumps(detail or {}),
            )
        except Exception:
            pass

    async def get_pipeline_history(self, pipeline_id: str, limit: int = 50) -> list[asyncpg.Record]:
        """获取操作历史；PG 不可用时返回空列表。"""
        if not self._pg:
            return []
        return await self._pg.fetch(
            "SELECT id, operation, operator, status, detail, created_at "
            "FROM pipeline_operations WHERE pipeline_id=$1 "
            "ORDER BY created_at DESC LIMIT $2",
            pipeline_id, limit,
        )

    # ------------------------------------------------------------------
    # 节点 / 边 结构化存储
    # ------------------------------------------------------------------

    async def clear_nodes(self, pipeline_id: str) -> None:
        await self._pg.execute("DELETE FROM pipeline_nodes WHERE pipeline_id=$1", pipeline_id)

    async def clear_edges(self, pipeline_id: str) -> None:
        await self._pg.execute("DELETE FROM pipeline_edges WHERE pipeline_id=$1", pipeline_id)

    async def upsert_node(
        self,
        pipeline_id: str,
        node_id: str,
        node_type: str,
        sub_type: str,
        label: str,
        config_json: str,
        pos_x: float,
        pos_y: float,
        sort_order: int,
    ) -> None:
        """INSERT ... ON CONFLICT DO UPDATE；单个节点异常时静默忽略。"""
        try:
            await self._pg.execute(
                "INSERT INTO pipeline_nodes (pipeline_id, node_id, node_type, sub_type, label, config, position_x, position_y, sort_order) "
                "VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8, $9) "
                "ON CONFLICT (pipeline_id, node_id) DO UPDATE SET "
                "node_type=$3, sub_type=$4, label=$5, config=$6::jsonb, position_x=$7, position_y=$8, sort_order=$9, updated_at=NOW()",
                pipeline_id, node_id, node_type, sub_type, label,
                config_json, pos_x, pos_y, sort_order,
            )
        except Exception:
            pass

    async def insert_edge(
        self,
        pipeline_id: str,
        source: str,
        target: str,
        edge_type: str,
        condition: str,
    ) -> None:
        """INSERT ... ON CONFLICT DO NOTHING；单条边异常时静默忽略。"""
        try:
            await self._pg.execute(
                "INSERT INTO pipeline_edges (pipeline_id, source_node_id, target_node_id, edge_type, condition) "
                "VALUES ($1, $2, $3, $4, $5) "
                "ON CONFLICT (pipeline_id, source_node_id, target_node_id) DO NOTHING",
                pipeline_id, source, target, edge_type, condition,
            )
        except Exception:
            pass

    async def load_nodes(self, pipeline_id: str) -> list[asyncpg.Record]:
        return await self._pg.fetch(
            "SELECT node_id, node_type, sub_type, label, config, position_x, position_y, sort_order "
            "FROM pipeline_nodes WHERE pipeline_id=$1 ORDER BY sort_order",
            pipeline_id,
        )

    async def load_edges(self, pipeline_id: str) -> list[asyncpg.Record]:
        return await self._pg.fetch(
            "SELECT source_node_id, target_node_id, edge_type, condition "
            "FROM pipeline_edges WHERE pipeline_id=$1",
            pipeline_id,
        )

    # ------------------------------------------------------------------
    # Replay jobs
    # ------------------------------------------------------------------

    async def create_replay_job(
        self,
        replay_id: str,
        pipeline: str,
        date: str,
        hour: int | None,
    ) -> None:
        """写入 replay_jobs；PG 不可用或异常时静默忽略。"""
        if not self._pg:
            return
        try:
            await self._pg.execute(
                "INSERT INTO replay_jobs (replay_id, pipeline, date, hour, status) "
                "VALUES ($1, $2, $3, $4, $5)",
                replay_id, pipeline, date, hour, "queued",
            )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Redis
    # ------------------------------------------------------------------

    async def set_redis_pipeline_status(self, pipeline_id: str, status: str) -> None:
        """写入 Redis 期望状态；不可用或异常时静默忽略。"""
        if not self._redis:
            return
        try:
            await self._redis.set(f"pipeline:{pipeline_id}:desired_status", status, ex=86400)
        except Exception:
            pass

    async def get_active_pipeline_count(self) -> int:
        """从 Redis ckpt:offset:* 键数量推断活跃 pipeline 数；不可用时返回 0。"""
        if not self._redis:
            return 0
        try:
            keys = await self._redis.keys("ckpt:offset:*")
            return len(keys)
        except Exception:
            return 0

    # ------------------------------------------------------------------
    # ES 聚合统计
    # ------------------------------------------------------------------

    async def get_es_pipeline_stats(self, index: str, body: dict) -> dict | None:
        """执行 ES search；不可用或异常时返回 None。"""
        if not self._es:
            return None
        try:
            return await self._es.search(index=index, body=body)
        except Exception:
            return None

    # ------------------------------------------------------------------
    # 文件系统 YAML
    # ------------------------------------------------------------------

    def list_pipeline_files(self, pipeline_dir: str) -> list[dict]:
        """扫描 dag_pipeline_dir/*.yaml，返回 pipeline info dict 列表（无 DB）。"""
        results: list[dict] = []
        dir_path = Path(pipeline_dir)
        if not dir_path.is_dir():
            return results
        for f in sorted(dir_path.glob("*.yaml")):
            try:
                meta = yaml.safe_load(f.read_text()) or {}
                results.append({
                    "pipeline_id": f.stem,
                    "name": meta.get("name", f.stem),
                    "mode": meta.get("mode", "unknown"),
                    "status": meta.get("status", "inactive"),
                    "version": meta.get("version", "0.0.0"),
                    "created_at": None,
                })
            except Exception:
                continue
        return results

    def read_pipeline_file(self, pipeline_dir: str, pipeline_id: str) -> dict | None:
        """从本地 YAML 文件读取单个 pipeline（PG fallback）；不存在时返回 None。"""
        yaml_path = Path("src/dag") / "pipelines" / f"{pipeline_id}.yaml"
        if not yaml_path.exists():
            return None
        content = yaml_path.read_text()
        meta = yaml.safe_load(content) or {}
        return {
            "pipeline_id": pipeline_id,
            "name": meta.get("name", pipeline_id),
            "mode": meta.get("mode", "unknown"),
            "status": meta.get("status", "inactive"),
            "version": meta.get("version", "0.0.0"),
            "yaml_content": content,
            "nodes": [],
            "edges": [],
        }

    # ------------------------------------------------------------------
    # Node config CRUD
    # ------------------------------------------------------------------

    async def list_node_configs(
        self,
        node_type: str | None = None,
        category: str | None = None,
    ) -> list[asyncpg.Record]:
        """查询 node_configs；PG 不可用时返回空列表。"""
        if not self._pg:
            return []
        sql = "SELECT * FROM node_configs WHERE 1=1"
        params: list = []
        if node_type:
            params.append(node_type)
            sql += f" AND node_type=${len(params)}"
        if category:
            params.append(category)
            sql += f" AND category=${len(params)}"
        sql += " ORDER BY updated_at DESC"
        return await self._pg.fetch(sql, *params)

    async def create_node_config(
        self,
        node_type: str,
        category: str,
        name: str,
        config_json: str,
        description: str,
    ) -> asyncpg.Record:
        """INSERT node_config RETURNING *；异常（含 UniqueViolation）向上传播。"""
        return await self._pg.fetchrow(
            "INSERT INTO node_configs (node_type, category, name, config, description) "
            "VALUES ($1, $2, $3, $4::jsonb, $5) RETURNING *",
            node_type, category, name, config_json, description,
        )

    async def get_node_config(self, config_id: int) -> asyncpg.Record | None:
        """获取单条 node_config；PG 不可用时返回 None。"""
        if not self._pg:
            return None
        return await self._pg.fetchrow("SELECT * FROM node_configs WHERE id=$1", config_id)

    async def update_node_config(
        self,
        config_id: int,
        name: str,
        config_json: str,
        description: str,
    ) -> None:
        await self._pg.execute(
            "UPDATE node_configs SET name=$1, config=$2::jsonb, description=$3, updated_at=NOW() WHERE id=$4",
            name, config_json, description, config_id,
        )

    async def delete_node_config(self, config_id: int) -> str:
        """删除 node_config，返回 execute 结果字符串。"""
        return await self._pg.execute("DELETE FROM node_configs WHERE id=$1", config_id)
