"""
Pipeline 业务逻辑层。
不依赖 FastAPI，只依赖 PipelineRepo。可独立单测。

涵盖：
  - YAML 解析与 _save_nodes_edges（节点类型映射、节点/边提取写入）
  - Pipeline CRUD、状态流转（start/stop/rollback）
  - Replay 触发、DAG status 聚合
  - 节点配置 schema 查询与 CRUD 校验
"""
from __future__ import annotations

import json
from uuid import uuid4

import yaml

from business.repositories.pipeline_repo import PipelineRepo
from business.services.node_schemas import NODE_CONFIG_SCHEMAS
from common.config import get_settings
from common.constants import ES_INDEX_EVENTS


# ---------------------------------------------------------------------------
# 自定义异常 — API 层捕获并转换为 HTTPException
# ---------------------------------------------------------------------------

class PipelineNotFoundError(LookupError):
    """Pipeline 在 DB 或文件系统中均不存在。"""


class DatabaseUnavailableError(ConnectionError):
    """PG pool 不可用（为 None）。"""


class PipelineSaveError(RuntimeError):
    """创建或更新 Pipeline 失败，detail 包含原始异常信息。"""

    def __init__(self, operation: str, original_exc: Exception) -> None:
        super().__init__(f"Failed to {operation} pipeline: {original_exc}")


class NodeTypeUnknownError(ValueError):
    """未知节点类型，不在 NODE_CONFIG_SCHEMAS 中。"""


class NodeConfigNotFoundError(LookupError):
    """Node config 记录不存在。"""


# ---------------------------------------------------------------------------
# PipelineService
# ---------------------------------------------------------------------------

# 节点子类型 → 节点大类 映射（原样保留，包括 "scoring_service" → "infer"）
_NODE_TYPE_MAP: dict[str, str] = {
    "kafka_consumer": "ingest", "file_reader": "ingest",
    "dns_parser": "transform", "feature_extractor": "transform",
    "scoring_service": "infer", "family_classify": "infer",
    "whitelist": "filter", "blacklist": "filter", "threshold": "filter", "severity_tag": "filter",
    "es_sink": "sink", "kafka_sink": "sink", "starrocks_sink": "sink", "multi_sink": "sink",
}


class PipelineService:
    """Pipeline 管理 + 节点配置 CRUD 的业务编排层；不做 HTTP。"""

    def __init__(self, repo: PipelineRepo) -> None:
        self._repo = repo

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    async def _record_operation(
        self,
        pipeline_id: str,
        operation: str,
        operator: str = "system",
        status: str = "success",
        detail: dict | None = None,
    ) -> None:
        """写入操作历史；委托 repo（repo 内部静默处理失败）。"""
        await self._repo.record_operation(pipeline_id, operation, operator, status, detail)

    async def _save_nodes_edges(self, pipeline_id: str, yaml_content: str) -> None:
        """解析 YAML 并将节点和边写入结构化表（先删后插）。逻辑原样保留。"""
        try:
            parsed = yaml.safe_load(yaml_content) or {}
        except Exception:
            return

        raw_nodes = parsed.get("nodes", [])
        raw_connections = parsed.get("connections", [])

        # 清除旧数据
        await self._repo.clear_nodes(pipeline_id)
        await self._repo.clear_edges(pipeline_id)

        # 写入节点
        for idx, node in enumerate(raw_nodes):
            node_id = node.get("id", f"node_{idx}")
            sub_type = node.get("type", "unknown")
            config = node.get("config", {})
            label = node.get("label", sub_type)
            node_type = _NODE_TYPE_MAP.get(sub_type, "transform")
            pos_x = node.get("position_x", idx * 200.0)
            pos_y = node.get("position_y", 100.0)
            await self._repo.upsert_node(
                pipeline_id, node_id, node_type, sub_type, label,
                json.dumps(config), pos_x, pos_y, idx,
            )

        # 写入边
        for conn in raw_connections:
            source = conn.get("source", "")
            target = conn.get("target", "")
            if not source or not target:
                continue
            edge_type = conn.get("edge_type", "default")
            condition = conn.get("condition", "")
            await self._repo.insert_edge(pipeline_id, source, target, edge_type, condition)

    async def _load_nodes_edges(
        self, pipeline_id: str
    ) -> tuple[list[dict], list[dict]]:
        """从结构化表加载节点和边，转换为 dict 列表。"""
        node_rows = await self._repo.load_nodes(pipeline_id)
        edge_rows = await self._repo.load_edges(pipeline_id)
        nodes = [
            {
                "node_id": r["node_id"],
                "node_type": r["node_type"],
                "sub_type": r["sub_type"],
                "label": r["label"],
                "config": json.loads(r["config"]) if isinstance(r["config"], str) else dict(r["config"]),
                "position_x": r["position_x"],
                "position_y": r["position_y"],
                "sort_order": r["sort_order"],
            }
            for r in node_rows
        ]
        edges = [
            {
                "source": r["source_node_id"],
                "target": r["target_node_id"],
                "edge_type": r["edge_type"],
                "condition": r["condition"],
            }
            for r in edge_rows
        ]
        return nodes, edges

    # ------------------------------------------------------------------
    # Pipeline 列表 / 统计
    # ------------------------------------------------------------------

    async def list_pipelines(self) -> dict:
        """列出所有 pipeline；PG 失败时回退到本地 YAML 文件。"""
        try:
            rows = await self._repo.list_pipelines()
            if rows is not None:
                pipelines = [
                    {
                        "pipeline_id": r["pipeline_id"],
                        "name": r["name"],
                        "mode": r["mode"],
                        "status": r["status"],
                        "version": r["version"],
                        "created_at": str(r["created_at"]) if r.get("created_at") else None,
                    }
                    for r in rows
                ]
                return {"pipelines": pipelines}
        except Exception:
            pass

        # Fallback: 扫描本地 YAML 文件
        files = self._repo.list_pipeline_files(get_settings().dag_pipeline_dir)
        return {"pipelines": files}

    async def pipeline_stats(self) -> dict:
        """Pipeline 统计概览：状态计数、告警分布、家族 Top10。"""
        status_counts: dict[str, int] = {"running": 0, "stopped": 0, "inactive": 0}
        total = 0
        pipeline_names: dict[str, str] = {}

        rows = await self._repo.count_pipeline_statuses()
        for r in rows:
            total += 1
            s = r["status"]
            status_counts[s] = status_counts.get(s, 0) + 1
            pipeline_names[r["pipeline_id"]] = r["name"]

        alerts_by_pipeline: list[dict] = []
        alerts_by_family: list[dict] = []
        alerts_by_severity: list[dict] = []
        pipeline_ids_with_alerts: set[str] = set()

        es_body = {
            "size": 0,
            "query": {"term": {"is_dga": True}},
            "aggs": {
                "by_pipeline": {"terms": {"field": "pipeline_id.keyword", "size": 10}},
                "by_family": {"terms": {"field": "family.keyword", "size": 10}},
                "by_severity": {"terms": {"field": "severity.keyword", "size": 5}},
            },
        }
        resp = await self._repo.get_es_pipeline_stats(f"{ES_INDEX_EVENTS}-*", es_body)
        if resp:
            aggs = resp.get("aggregations", {})
            for b in aggs.get("by_pipeline", {}).get("buckets", []):
                pid = b["key"]
                pipeline_ids_with_alerts.add(pid)
                alerts_by_pipeline.append({
                    "pipeline_id": pid,
                    "name": pipeline_names.get(pid, pid[:8]),
                    "count": b["doc_count"],
                })
            for b in aggs.get("by_family", {}).get("buckets", []):
                alerts_by_family.append({"name": b["key"], "value": b["doc_count"]})
            for b in aggs.get("by_severity", {}).get("buckets", []):
                alerts_by_severity.append({"name": b["key"], "value": b["doc_count"]})

        alert_rate = round(len(pipeline_ids_with_alerts) / max(total, 1) * 100, 1)
        return {
            "total": total,
            "running": status_counts.get("running", 0),
            "stopped": status_counts.get("stopped", 0),
            "inactive": status_counts.get("inactive", 0),
            "alert_rate": alert_rate,
            "alerts_by_pipeline": alerts_by_pipeline,
            "alerts_by_family": alerts_by_family,
            "alerts_by_severity": alerts_by_severity,
        }

    # ------------------------------------------------------------------
    # Pipeline 详情 / CRUD
    # ------------------------------------------------------------------

    async def get_pipeline(self, pipeline_id: str) -> dict:
        """获取 pipeline 详情（含节点/边）；不存在时 raise PipelineNotFoundError。"""
        try:
            if self._repo.has_pg():
                row = await self._repo.get_pipeline(pipeline_id)
                if not row:
                    raise PipelineNotFoundError("Pipeline not found")
                nodes, edges = await self._load_nodes_edges(pipeline_id)
                return {
                    "pipeline_id": row["pipeline_id"],
                    "name": row["name"],
                    "mode": row["mode"],
                    "status": row["status"],
                    "version": row["version"],
                    "yaml_content": row.get("yaml_content", ""),
                    "nodes": nodes,
                    "edges": edges,
                }
        except PipelineNotFoundError:
            raise  # 已确认不存在，不 fallback 到文件系统
        except Exception:
            pass  # 其他错误 fallback

        # Fallback: 本地 YAML 文件
        data = self._repo.read_pipeline_file("", pipeline_id)
        if data is None:
            raise PipelineNotFoundError("Pipeline not found")
        return data

    async def create_pipeline(self, name: str, mode: str, yaml_content: str) -> dict:
        """创建新 pipeline；DB 不可用 → DatabaseUnavailableError；DB 写入失败 → PipelineSaveError。"""
        if not self._repo.has_pg():
            raise DatabaseUnavailableError("Database unavailable")
        pipeline_id = str(uuid4())
        version = 1
        try:
            await self._repo.create_pipeline(
                pipeline_id, name, mode, yaml_content, "inactive", str(version)
            )
            await self._save_nodes_edges(pipeline_id, yaml_content)
        except (DatabaseUnavailableError,):
            raise
        except Exception as exc:
            raise PipelineSaveError("create", exc)
        await self._record_operation(pipeline_id, "create", detail={"version": version})
        return {
            "pipeline_id": pipeline_id,
            "name": name,
            "mode": mode,
            "status": "inactive",
            "version": version,
        }

    async def delete_pipeline(self, pipeline_id: str) -> dict:
        """删除 pipeline；DB 不可用 → DatabaseUnavailableError；不存在 → PipelineNotFoundError。"""
        if not self._repo.has_pg():
            raise DatabaseUnavailableError("Database unavailable")
        try:
            result = await self._repo.delete_pipeline(pipeline_id)
            if result == "DELETE 0":
                raise PipelineNotFoundError("Pipeline not found")
        except (DatabaseUnavailableError, PipelineNotFoundError):
            raise
        except Exception as exc:
            raise PipelineSaveError("delete", exc)
        return {"ok": True}

    async def update_pipeline(
        self,
        pipeline_id: str,
        yaml_content: str,
        name: str | None = None,
        mode: str | None = None,
    ) -> dict:
        """更新 pipeline（版本号 +1）；不可用/不存在/失败时相应异常。"""
        if not self._repo.has_pg():
            raise DatabaseUnavailableError("Database unavailable")
        row = await self._repo.get_pipeline_meta(pipeline_id)
        if not row:
            raise PipelineNotFoundError("Pipeline not found")
        new_version = int(row["version"]) + 1
        new_name = name if name is not None else row["name"]
        new_mode = mode if mode is not None else row["mode"]
        try:
            await self._repo.update_pipeline(
                pipeline_id, new_name, new_mode, yaml_content, str(new_version)
            )
            await self._save_nodes_edges(pipeline_id, yaml_content)
        except (DatabaseUnavailableError, PipelineNotFoundError):
            raise
        except Exception as exc:
            raise PipelineSaveError("update", exc)
        await self._record_operation(pipeline_id, "save", detail={"version": new_version})
        return {
            "pipeline_id": pipeline_id,
            "name": new_name,
            "mode": new_mode,
            "status": row["status"],
            "version": new_version,
        }

    async def rollback_pipeline(self, pipeline_id: str, target_version: int) -> dict:
        """回滚 pipeline（仅记录操作历史，原地单行模式）。"""
        if not self._repo.has_pg():
            raise DatabaseUnavailableError("Database unavailable")
        row = await self._repo.get_pipeline_version(pipeline_id)
        if not row:
            raise PipelineNotFoundError("Pipeline not found")
        await self._record_operation(
            pipeline_id, "rollback", detail={"target_version": target_version}
        )
        return {
            "pipeline_id": pipeline_id,
            "current_version": row["version"],
            "note": "rollback recorded",
        }

    # ------------------------------------------------------------------
    # Pipeline 状态流转
    # ------------------------------------------------------------------

    async def start_pipeline(self, pipeline_id: str) -> dict:
        """启动 pipeline：写 Redis 期望状态 + 更新 PG status。"""
        await self._repo.set_redis_pipeline_status(pipeline_id, "running")
        await self._repo.set_pipeline_status(pipeline_id, "running")
        await self._record_operation(pipeline_id, "start")
        return {"ok": True, "status": "running"}

    async def stop_pipeline(self, pipeline_id: str) -> dict:
        """停止 pipeline：写 Redis 期望状态 + 更新 PG status。"""
        await self._repo.set_redis_pipeline_status(pipeline_id, "stopped")
        await self._repo.set_pipeline_status(pipeline_id, "stopped")
        await self._record_operation(pipeline_id, "stop")
        return {"ok": True, "status": "stopped"}

    # ------------------------------------------------------------------
    # Replay / DAG status / 历史
    # ------------------------------------------------------------------

    async def trigger_replay(
        self, pipeline: str, date: str, hour: int | None = None
    ) -> dict:
        """触发批量回放/补算，写入 replay_jobs 并记录操作历史。"""
        replay_id = str(uuid4())
        await self._repo.create_replay_job(replay_id, pipeline, date, hour)
        await self._record_operation(
            pipeline, "replay",
            detail={"replay_id": replay_id, "date": date, "hour": hour},
        )
        return {"replay_id": replay_id, "status": "queued", "stats": {}}

    async def dag_status(self) -> dict:
        """获取 DAG 引擎运行状态（活跃 pipeline 计数来自 Redis）。"""
        active_pipelines = await self._repo.get_active_pipeline_count()
        return {
            "active_pipelines": active_pipelines,
            "total_processed": 0,
            "errors": 0,
        }

    async def pipeline_history(self, pipeline_id: str, limit: int = 50) -> dict:
        """获取 pipeline 操作历史。"""
        rows = await self._repo.get_pipeline_history(pipeline_id, limit)
        return {
            "history": [
                {
                    "id": r["id"],
                    "operation": r["operation"],
                    "operator": r["operator"],
                    "status": r["status"],
                    "detail": (
                        json.loads(r["detail"])
                        if isinstance(r.get("detail"), str)
                        else (dict(r["detail"]) if r.get("detail") else {})
                    ),
                    "created_at": str(r["created_at"]),
                }
                for r in rows
            ]
        }

    # ------------------------------------------------------------------
    # 节点配置 Schema 查询
    # ------------------------------------------------------------------

    def list_schemas(self) -> dict:
        """返回全部 NODE_CONFIG_SCHEMAS。"""
        return {"schemas": NODE_CONFIG_SCHEMAS}

    def get_schema(self, node_type: str) -> dict:
        """返回指定节点类型 schema；未知类型 → NodeTypeUnknownError。"""
        schema = NODE_CONFIG_SCHEMAS.get(node_type)
        if not schema:
            raise NodeTypeUnknownError(f"Unknown node type: {node_type}")
        return {"node_type": node_type, **schema}

    # ------------------------------------------------------------------
    # 节点配置 CRUD
    # ------------------------------------------------------------------

    async def list_node_configs(
        self, node_type: str | None = None, category: str | None = None
    ) -> dict:
        """查询 node_configs，支持按 node_type/category 过滤。"""
        rows = await self._repo.list_node_configs(node_type, category)
        return {
            "configs": [
                {
                    "id": r["id"],
                    "node_type": r["node_type"],
                    "category": r["category"],
                    "name": r["name"],
                    "config": (
                        json.loads(r["config"])
                        if isinstance(r["config"], str)
                        else (dict(r["config"]) if r["config"] else {})
                    ),
                    "description": r["description"] or "",
                    "created_at": str(r["created_at"]),
                    "updated_at": str(r["updated_at"]),
                }
                for r in rows
            ]
        }

    async def create_node_config(
        self,
        node_type: str,
        name: str,
        config: dict,
        description: str,
    ) -> dict:
        """创建 node_config；未知类型 → NodeTypeUnknownError；DB 不可用 → DatabaseUnavailableError。
        asyncpg.UniqueViolationError 向上传播，由 API 层捕获转为 409。
        """
        schema = NODE_CONFIG_SCHEMAS.get(node_type)
        if not schema:
            raise NodeTypeUnknownError(f"Unknown node type: {node_type}")
        if not self._repo.has_pg():
            raise DatabaseUnavailableError("Database unavailable")
        row = await self._repo.create_node_config(
            node_type, schema["category"], name, json.dumps(config), description
        )
        return {
            "id": row["id"],
            "node_type": row["node_type"],
            "category": row["category"],
            "name": row["name"],
            "config": (
                json.loads(row["config"])
                if isinstance(row["config"], str)
                else (dict(row["config"]) if row["config"] else {})
            ),
            "description": row["description"] or "",
        }

    async def get_node_config(self, config_id: int) -> dict:
        """获取单条 node_config；DB 不可用 → DatabaseUnavailableError；不存在 → NodeConfigNotFoundError。"""
        if not self._repo.has_pg():
            raise DatabaseUnavailableError("Database unavailable")
        row = await self._repo.get_node_config(config_id)
        if not row:
            raise NodeConfigNotFoundError("Config not found")
        return {
            "id": row["id"],
            "node_type": row["node_type"],
            "category": row["category"],
            "name": row["name"],
            "config": (
                json.loads(row["config"])
                if isinstance(row["config"], str)
                else (dict(row["config"]) if row["config"] else {})
            ),
            "description": row["description"] or "",
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
        }

    async def update_node_config(
        self,
        config_id: int,
        name: str | None = None,
        config: dict | None = None,
        description: str | None = None,
    ) -> dict:
        """更新 node_config 字段（None 表示保留原值）。"""
        if not self._repo.has_pg():
            raise DatabaseUnavailableError("Database unavailable")
        row = await self._repo.get_node_config(config_id)
        if not row:
            raise NodeConfigNotFoundError("Config not found")
        new_name = name if name is not None else row["name"]
        new_config = (
            json.dumps(config)
            if config is not None
            else (
                row["config"]
                if isinstance(row["config"], str)
                else json.dumps(dict(row["config"]) if row["config"] else {})
            )
        )
        new_desc = description if description is not None else (row["description"] or "")
        await self._repo.update_node_config(config_id, new_name, new_config, new_desc)
        return {"ok": True, "id": config_id}

    async def delete_node_config(self, config_id: int) -> dict:
        """删除 node_config；DB 不可用 → DatabaseUnavailableError；不存在 → NodeConfigNotFoundError。"""
        if not self._repo.has_pg():
            raise DatabaseUnavailableError("Database unavailable")
        result = await self._repo.delete_node_config(config_id)
        if result == "DELETE 0":
            raise NodeConfigNotFoundError("Config not found")
        return {"ok": True}
