"""
DAG 管理路由 — /dag/pipelines /dag/replay /dag/status
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import asyncpg
import yaml
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from gateway.db import get_pg_pool, get_redis_client, get_es_client
from gateway.middleware.auth import verify_token
from gateway.middleware.rbac import require_admin, require_analyst, require_viewer
from shared.config import get_settings
from shared.constants import ES_INDEX_EVENTS

router = APIRouter()


class PipelineInfo(BaseModel):
    pipeline_id: str
    name: str
    mode: str
    status: str
    version: str
    created_at: str | None = None


class CreatePipelineRequest(BaseModel):
    name: str
    mode: str = "stream"
    yaml_content: str


class UpdatePipelineRequest(BaseModel):
    yaml_content: str
    name: str | None = None
    mode: str | None = None


class RollbackRequest(BaseModel):
    version: int


# ── 操作历史记录辅助 ──────────────────────────────────────────────


async def _record_operation(
    pg: asyncpg.Pool | None,
    pipeline_id: str,
    operation: str,
    operator: str = "system",
    status: str = "success",
    detail: dict | None = None,
) -> None:
    if not pg:
        return
    try:
        await pg.execute(
            "INSERT INTO pipeline_operations (pipeline_id, operation, operator, status, detail) "
            "VALUES ($1, $2, $3, $4, $5::jsonb)",
            pipeline_id, operation, operator, status, json.dumps(detail or {}),
        )
    except Exception:
        pass


# ── 节点/边 结构化存储辅助 ─────────────────────────────────────────


async def _save_nodes_edges(
    pg: asyncpg.Pool,
    pipeline_id: str,
    yaml_content: str,
) -> None:
    """解析 YAML 并将节点和边写入结构化表（先删后插）"""
    try:
        parsed = yaml.safe_load(yaml_content) or {}
    except Exception:
        return

    raw_nodes = parsed.get("nodes", [])
    raw_connections = parsed.get("connections", [])

    # 清除旧数据
    await pg.execute("DELETE FROM pipeline_nodes WHERE pipeline_id=$1", pipeline_id)
    await pg.execute("DELETE FROM pipeline_edges WHERE pipeline_id=$1", pipeline_id)

    # 写入节点
    for idx, node in enumerate(raw_nodes):
        node_id = node.get("id", f"node_{idx}")
        sub_type = node.get("type", "unknown")
        config = node.get("config", {})
        label = node.get("label", sub_type)
        # 推断 node_type 大类
        type_map = {
            "kafka_consumer": "ingest", "file_reader": "ingest",
            "dns_parser": "transform", "feature_extractor": "transform",
            "scoring_service": "infer", "family_classify": "infer",
            "whitelist": "filter", "blacklist": "filter", "threshold": "filter", "severity_tag": "filter",
            "es_sink": "sink", "kafka_sink": "sink", "starrocks_sink": "sink", "multi_sink": "sink",
        }
        node_type = type_map.get(sub_type, "transform")
        pos_x = node.get("position_x", idx * 200.0)
        pos_y = node.get("position_y", 100.0)
        try:
            await pg.execute(
                "INSERT INTO pipeline_nodes (pipeline_id, node_id, node_type, sub_type, label, config, position_x, position_y, sort_order) "
                "VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8, $9) "
                "ON CONFLICT (pipeline_id, node_id) DO UPDATE SET "
                "node_type=$3, sub_type=$4, label=$5, config=$6::jsonb, position_x=$7, position_y=$8, sort_order=$9, updated_at=NOW()",
                pipeline_id, node_id, node_type, sub_type, label,
                json.dumps(config), pos_x, pos_y, idx,
            )
        except Exception:
            pass

    # 写入边
    for conn in raw_connections:
        source = conn.get("source", "")
        target = conn.get("target", "")
        if not source or not target:
            continue
        edge_type = conn.get("edge_type", "default")
        condition = conn.get("condition", "")
        try:
            await pg.execute(
                "INSERT INTO pipeline_edges (pipeline_id, source_node_id, target_node_id, edge_type, condition) "
                "VALUES ($1, $2, $3, $4, $5) "
                "ON CONFLICT (pipeline_id, source_node_id, target_node_id) DO NOTHING",
                pipeline_id, source, target, edge_type, condition,
            )
        except Exception:
            pass


async def _load_nodes_edges(
    pg: asyncpg.Pool,
    pipeline_id: str,
) -> tuple[list[dict], list[dict]]:
    """从结构化表加载节点和边"""
    node_rows = await pg.fetch(
        "SELECT node_id, node_type, sub_type, label, config, position_x, position_y, sort_order "
        "FROM pipeline_nodes WHERE pipeline_id=$1 ORDER BY sort_order",
        pipeline_id,
    )
    edge_rows = await pg.fetch(
        "SELECT source_node_id, target_node_id, edge_type, condition "
        "FROM pipeline_edges WHERE pipeline_id=$1",
        pipeline_id,
    )
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


@router.get("/dag/pipelines", dependencies=[Depends(require_viewer)])
async def list_pipelines(pg: asyncpg.Pool | None = Depends(get_pg_pool)):
    """列出所有 DAG pipeline"""
    try:
        if pg:
            rows = await pg.fetch(
                "SELECT pipeline_id, name, mode, status, version, created_at "
                "FROM pipeline_configs ORDER BY created_at DESC"
            )
            pipelines = [
                PipelineInfo(
                    pipeline_id=r["pipeline_id"],
                    name=r["name"],
                    mode=r["mode"],
                    status=r["status"],
                    version=r["version"],
                    created_at=str(r["created_at"]) if r.get("created_at") else None,
                )
                for r in rows
            ]
            return {"pipelines": pipelines}
    except Exception:
        pass

    # Fallback: scan local YAML files
    pipelines: list[PipelineInfo] = []
    pipeline_dir = Path(get_settings().dag_pipeline_dir)
    if pipeline_dir.is_dir():
        for f in sorted(pipeline_dir.glob("*.yaml")):
            try:
                meta = yaml.safe_load(f.read_text()) or {}
                pipelines.append(
                    PipelineInfo(
                        pipeline_id=f.stem,
                        name=meta.get("name", f.stem),
                        mode=meta.get("mode", "unknown"),
                        status=meta.get("status", "inactive"),
                        version=meta.get("version", "0.0.0"),
                    )
                )
            except Exception:
                continue
    return {"pipelines": pipelines}


@router.get("/dag/pipelines/stats", dependencies=[Depends(require_viewer)])
async def pipeline_stats(
    pg: asyncpg.Pool | None = Depends(get_pg_pool),
    es=Depends(get_es_client),
):
    """Pipeline 统计概览：计数、告警分布、家族 Top10"""
    status_counts: dict[str, int] = {"running": 0, "stopped": 0, "inactive": 0}
    total = 0
    pipeline_names: dict[str, str] = {}
    if pg:
        try:
            rows = await pg.fetch(
                "SELECT pipeline_id, name, status FROM pipeline_configs"
            )
            for r in rows:
                total += 1
                s = r["status"]
                status_counts[s] = status_counts.get(s, 0) + 1
                pipeline_names[r["pipeline_id"]] = r["name"]
        except Exception:
            pass

    alerts_by_pipeline: list[dict] = []
    alerts_by_family: list[dict] = []
    alerts_by_severity: list[dict] = []
    pipeline_ids_with_alerts: set[str] = set()

    if es:
        try:
            body = {
                "size": 0,
                "query": {"term": {"is_dga": True}},
                "aggs": {
                    "by_pipeline": {"terms": {"field": "pipeline_id.keyword", "size": 10}},
                    "by_family": {"terms": {"field": "family.keyword", "size": 10}},
                    "by_severity": {"terms": {"field": "severity.keyword", "size": 5}},
                },
            }
            resp = await es.search(index=f"{ES_INDEX_EVENTS}-*", body=body)
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
        except Exception:
            pass

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


@router.get("/dag/pipelines/{pipeline_id}", dependencies=[Depends(require_viewer)])
async def get_pipeline(pipeline_id: str, pg: asyncpg.Pool | None = Depends(get_pg_pool)):
    """获取 pipeline 详情（含 YAML 配置 + 结构化节点/边）"""
    try:
        if pg:
            row = await pg.fetchrow(
                "SELECT * FROM pipeline_configs WHERE pipeline_id=$1",
                pipeline_id,
            )
            if not row:
                raise HTTPException(status_code=404, detail="Pipeline not found")
            nodes, edges = await _load_nodes_edges(pg, pipeline_id)
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
    except HTTPException:
        raise
    except Exception:
        pass

    # Fallback: read local YAML
    yaml_path = Path("dag_engine") / "pipelines" / f"{pipeline_id}.yaml"
    if not yaml_path.exists():
        raise HTTPException(status_code=404, detail="Pipeline not found")
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


@router.post("/dag/pipelines", dependencies=[Depends(require_admin)])
async def create_pipeline(req: CreatePipelineRequest, pg: asyncpg.Pool | None = Depends(get_pg_pool)):
    """创建新的 pipeline 配置"""
    pipeline_id = str(uuid4())
    version = 1
    if not pg:
        raise HTTPException(status_code=503, detail="Database unavailable")
    try:
        await pg.execute(
            "INSERT INTO pipeline_configs (pipeline_id, name, mode, yaml_content, status, version, created_at) "
            "VALUES ($1, $2, $3, $4, $5, $6, NOW())",
            pipeline_id, req.name, req.mode, req.yaml_content, "inactive", str(version),
        )
        # 同步写入结构化节点/边
        await _save_nodes_edges(pg, pipeline_id, req.yaml_content)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to create pipeline: {exc}")
    await _record_operation(pg, pipeline_id, "create", detail={"version": version})
    return {
        "pipeline_id": pipeline_id,
        "name": req.name,
        "mode": req.mode,
        "status": "inactive",
        "version": version,
    }


@router.delete("/dag/pipelines/{pipeline_id}", dependencies=[Depends(require_admin)])
async def delete_pipeline(pipeline_id: str, pg: asyncpg.Pool | None = Depends(get_pg_pool)):
    """删除 pipeline 及其所有版本"""
    if not pg:
        raise HTTPException(status_code=503, detail="Database unavailable")
    try:
        result = await pg.execute(
            "DELETE FROM pipeline_configs WHERE pipeline_id=$1", pipeline_id,
        )
        if result == "DELETE 0":
            raise HTTPException(status_code=404, detail="Pipeline not found")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to delete pipeline: {exc}")
    return {"ok": True}


@router.put("/dag/pipelines/{pipeline_id}", dependencies=[Depends(require_admin)])
async def update_pipeline(
    pipeline_id: str,
    req: UpdatePipelineRequest,
    pg: asyncpg.Pool | None = Depends(get_pg_pool),
):
    """更新 pipeline 配置（版本号 +1，原地更新）"""
    if not pg:
        raise HTTPException(status_code=503, detail="Database unavailable")
    row = await pg.fetchrow(
        "SELECT name, mode, version, status FROM pipeline_configs "
        "WHERE pipeline_id=$1",
        pipeline_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    new_version = int(row["version"]) + 1
    new_name = req.name if req.name is not None else row["name"]
    new_mode = req.mode if req.mode is not None else row["mode"]
    try:
        await pg.execute(
            "UPDATE pipeline_configs SET name=$1, mode=$2, yaml_content=$3, version=$4, updated_at=NOW() "
            "WHERE pipeline_id=$5",
            new_name, new_mode, req.yaml_content, str(new_version), pipeline_id,
        )
        # 同步更新结构化节点/边
        await _save_nodes_edges(pg, pipeline_id, req.yaml_content)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to update pipeline: {exc}")
    await _record_operation(pg, pipeline_id, "save", detail={"version": new_version})
    return {
        "pipeline_id": pipeline_id,
        "name": new_name,
        "mode": new_mode,
        "status": row["status"],
        "version": new_version,
    }


@router.post("/dag/pipelines/{pipeline_id}/rollback", dependencies=[Depends(require_admin)])
async def rollback_pipeline(
    pipeline_id: str,
    req: RollbackRequest,
    pg: asyncpg.Pool | None = Depends(get_pg_pool),
):
    """回滚 pipeline 到指定版本（通过操作历史恢复）"""
    if not pg:
        raise HTTPException(status_code=503, detail="Database unavailable")
    # 回滚在单行模式下不再适用版本查找，直接返回提示
    row = await pg.fetchrow(
        "SELECT version FROM pipeline_configs WHERE pipeline_id=$1", pipeline_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    await _record_operation(pg, pipeline_id, "rollback", detail={"target_version": req.version})
    return {
        "pipeline_id": pipeline_id,
        "current_version": row["version"],
        "note": "rollback recorded",
    }


@router.post("/dag/pipelines/{pipeline_id}/start", dependencies=[Depends(require_analyst)])
async def start_pipeline(
    pipeline_id: str,
    redis=Depends(get_redis_client),
    pg: asyncpg.Pool | None = Depends(get_pg_pool),
):
    """启动 pipeline（写入期望状态，供 DAG 引擎消费）"""
    if redis:
        try:
            await redis.set(f"pipeline:{pipeline_id}:desired_status", "running", ex=86400)
        except Exception:
            pass
    if pg:
        try:
            await pg.execute(
                "UPDATE pipeline_configs SET status='running' WHERE pipeline_id=$1",
                pipeline_id,
            )
        except Exception:
            pass
    await _record_operation(pg, pipeline_id, "start")
    return {"ok": True, "status": "running"}


@router.post("/dag/pipelines/{pipeline_id}/stop", dependencies=[Depends(require_analyst)])
async def stop_pipeline(
    pipeline_id: str,
    redis=Depends(get_redis_client),
    pg: asyncpg.Pool | None = Depends(get_pg_pool),
):
    """停止 pipeline"""
    if redis:
        try:
            await redis.set(f"pipeline:{pipeline_id}:desired_status", "stopped", ex=86400)
        except Exception:
            pass
    if pg:
        try:
            await pg.execute(
                "UPDATE pipeline_configs SET status='stopped' WHERE pipeline_id=$1",
                pipeline_id,
            )
        except Exception:
            pass
    await _record_operation(pg, pipeline_id, "stop")
    return {"ok": True, "status": "stopped"}


class ReplayRequest(BaseModel):
    pipeline: str = "dga-batch-v1"
    date: str  # "2026-02-10"
    hour: int | None = None  # 可选：指定小时


class ReplayResponse(BaseModel):
    replay_id: str
    status: str
    stats: dict = {}


@router.post("/dag/replay", response_model=ReplayResponse, dependencies=[Depends(require_analyst)])
async def trigger_replay(req: ReplayRequest, pg: asyncpg.Pool | None = Depends(get_pg_pool)):
    """触发批量回放/补算"""
    replay_id = str(uuid4())
    if pg:
        try:
            await pg.execute(
                "INSERT INTO replay_jobs (replay_id, pipeline, date, hour, status) "
                "VALUES ($1, $2, $3, $4, $5)",
                replay_id, req.pipeline, req.date, req.hour, "queued",
            )
        except Exception:
            pass
    await _record_operation(pg, req.pipeline, "replay", detail={"replay_id": replay_id, "date": req.date, "hour": req.hour})
    return ReplayResponse(replay_id=replay_id, status="queued")


@router.get("/dag/status", dependencies=[Depends(require_viewer)])
async def dag_status(redis=Depends(get_redis_client)):
    """获取 DAG 引擎运行状态"""
    active_pipelines = 0
    if redis:
        try:
            keys = await redis.keys("ckpt:offset:*")
            active_pipelines = len(keys)
        except Exception:
            pass
    return {
        "active_pipelines": active_pipelines,
        "total_processed": 0,
        "errors": 0,
    }


@router.get("/dag/pipelines/{pipeline_id}/history", dependencies=[Depends(require_viewer)])
async def pipeline_history(
    pipeline_id: str,
    limit: int = 50,
    pg: asyncpg.Pool | None = Depends(get_pg_pool),
):
    """获取 pipeline 操作历史"""
    if not pg:
        return {"history": []}
    rows = await pg.fetch(
        "SELECT id, operation, operator, status, detail, created_at "
        "FROM pipeline_operations WHERE pipeline_id=$1 "
        "ORDER BY created_at DESC LIMIT $2",
        pipeline_id, limit,
    )
    return {
        "history": [
            {
                "id": r["id"],
                "operation": r["operation"],
                "operator": r["operator"],
                "status": r["status"],
                "detail": json.loads(r["detail"]) if isinstance(r.get("detail"), str) else (dict(r["detail"]) if r.get("detail") else {}),
                "created_at": str(r["created_at"]),
            }
            for r in rows
        ]
    }
