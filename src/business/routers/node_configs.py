"""
节点配置管理路由 — /node-configs CRUD
提供 13 种 DAG 节点类型的配置 schema 查询与持久化管理
"""

from __future__ import annotations

import json

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from business.db import get_pg_pool
from business.middleware.rbac import require_admin, require_viewer

router = APIRouter()

# ── 预定义节点配置 Schema ──────────────────────────────────────────

NODE_CONFIG_SCHEMAS: dict[str, dict] = {
    "kafka_consumer": {
        "category": "ingest",
        "fields": [
            {"key": "topic", "type": "string", "label": "Kafka Topic", "required": True, "default": "dns-query-logs"},
            {"key": "group_id", "type": "string", "label": "Consumer Group", "required": True, "default": "dga-detector-v1"},
            {"key": "bootstrap_servers", "type": "string", "label": "Bootstrap Servers", "default": "kafka:9092"},
            {"key": "auto_offset_reset", "type": "enum", "label": "Offset Reset", "options": ["earliest", "latest"], "default": "earliest"},
        ],
    },
    "file_reader": {
        "category": "ingest",
        "fields": [
            {"key": "directory", "type": "string", "label": "目录路径", "required": True, "default": "/data/dns-logs"},
            {"key": "pattern", "type": "string", "label": "文件匹配模式", "default": "*.csv"},
            {"key": "batch_size", "type": "number", "label": "批次大小", "default": 1000},
        ],
    },
    "dns_parser": {
        "category": "transform",
        "fields": [
            {"key": "fields", "type": "array", "label": "解析字段", "default": ["query_name", "query_type", "src_ip", "timestamp"]},
        ],
    },
    "feature_extractor": {
        "category": "transform",
        "fields": [
            {"key": "extractors", "type": "array", "label": "特征提取器", "default": ["lexical", "entropy", "ngram"]},
        ],
    },
    "scoring_service": {
        "category": "infer",
        "fields": [
            {"key": "endpoint", "type": "string", "label": "服务地址", "required": True, "default": "scoring-service:50051"},
            {"key": "timeout_ms", "type": "number", "label": "超时(ms)", "default": 100},
            {"key": "model_version", "type": "string", "label": "模型版本", "default": "latest"},
        ],
    },
    "whitelist": {
        "category": "filter",
        "fields": [
            {"key": "source", "type": "string", "label": "白名单来源", "default": "redis"},
            {"key": "key", "type": "string", "label": "Redis Key", "default": "whitelist:domains"},
            {"key": "ttl", "type": "number", "label": "缓存TTL(秒)", "default": 3600},
        ],
    },
    "threshold": {
        "category": "filter",
        "fields": [
            {"key": "min_score", "type": "number", "label": "最低分数", "default": 0.5},
            {"key": "max_score", "type": "number", "label": "最高分数", "default": 1.0},
        ],
    },
    "blacklist": {
        "category": "filter",
        "fields": [
            {"key": "source", "type": "string", "label": "黑名单来源", "default": "redis"},
            {"key": "key", "type": "string", "label": "Redis Key", "default": "blacklist:domains"},
        ],
    },
    "es_sink": {
        "category": "sink",
        "fields": [
            {"key": "index_prefix", "type": "string", "label": "索引前缀", "required": True, "default": "dga-events"},
            {"key": "hosts", "type": "string", "label": "ES 地址", "default": "http://elasticsearch:9200"},
        ],
    },
    "kafka_sink": {
        "category": "sink",
        "fields": [
            {"key": "topic", "type": "string", "label": "输出 Topic", "required": True, "default": "dga-alerts"},
            {"key": "bootstrap_servers", "type": "string", "label": "Bootstrap Servers", "default": "kafka:9092"},
        ],
    },
    "starrocks_sink": {
        "category": "sink",
        "fields": [
            {"key": "database", "type": "string", "label": "数据库", "default": "dga_analytics"},
            {"key": "table", "type": "string", "label": "表名", "default": "dga_events"},
            {"key": "hosts", "type": "string", "label": "FE 地址", "default": "starrocks:8030"},
        ],
    },
    "fan_out": {
        "category": "sink",
        "fields": [
            {"key": "targets", "type": "array", "label": "输出目标", "default": []},
        ],
    },
    "multi_sink": {
        "category": "sink",
        "fields": [
            {"key": "routes", "type": "array", "label": "路由规则", "default": []},
            {"key": "default_target", "type": "enum", "label": "默认输出", "options": ["es", "kafka", "starrocks", "drop"], "default": "es"},
            {"key": "es_index", "type": "string", "label": "ES 索引", "default": "dga-events"},
            {"key": "kafka_topic", "type": "string", "label": "Kafka Topic", "default": "dga-alerts"},
            {"key": "starrocks_table", "type": "string", "label": "StarRocks 表", "default": "dga_events"},
        ],
    },
    "es_source": {
        "category": "ingest",
        "fields": [
            {"key": "hosts", "type": "string", "label": "ES 集群地址", "required": True, "default": "http://elasticsearch:9200"},
            {"key": "index", "type": "string", "label": "索引模式", "required": True, "default": "dns-logs-*"},
            {"key": "query", "type": "string", "label": "查询 DSL (JSON)"},
            {"key": "scroll_size", "type": "number", "label": "每次滚动条数", "default": 1000},
            {"key": "scroll_timeout", "type": "string", "label": "滚动超时", "default": "5m"},
            {"key": "fields", "type": "array", "label": "返回字段", "default": ["domain", "src_ip", "timestamp"]},
        ],
    },
    "severity_tag": {
        "category": "transform",
        "fields": [
            {"key": "critical_threshold", "type": "number", "label": "CRITICAL 阈值 (>=)", "default": 0.95},
            {"key": "high_threshold", "type": "number", "label": "HIGH 阈值 (>=)", "default": 0.85},
            {"key": "medium_threshold", "type": "number", "label": "MEDIUM 阈值 (>=)", "default": 0.7},
            {"key": "score_field", "type": "string", "label": "分数字段", "default": "score"},
            {"key": "output_field", "type": "string", "label": "输出字段", "default": "severity"},
        ],
    },
    "threat_intel_enrich": {
        "category": "transform",
        "fields": [
            {"key": "providers", "type": "array", "label": "情报源", "required": True, "default": ["virustotal"]},
            {"key": "api_key_env", "type": "string", "label": "API Key 环境变量"},
            {"key": "cache_ttl", "type": "number", "label": "缓存 TTL (秒)", "default": 3600},
            {"key": "timeout_ms", "type": "number", "label": "查询超时 (ms)", "default": 5000},
            {"key": "enrich_fields", "type": "array", "label": "富化字段", "default": ["reputation", "malware_family"]},
            {"key": "fail_open", "type": "boolean", "label": "查询失败时放行", "default": True},
        ],
    },
    "geoip_lookup": {
        "category": "transform",
        "fields": [
            {"key": "ip_field", "type": "string", "label": "IP 字段", "required": True, "default": "src_ip"},
            {"key": "database", "type": "enum", "label": "GeoIP 数据库", "options": ["maxmind", "ip2location", "dbip"], "default": "maxmind"},
            {"key": "db_path", "type": "string", "label": "数据库文件路径"},
            {"key": "output_fields", "type": "array", "label": "输出字段", "default": ["country", "city", "asn"]},
            {"key": "high_risk_countries", "type": "array", "label": "高风险国家代码", "default": []},
        ],
    },
    "risk_aggregate": {
        "category": "transform",
        "fields": [
            {"key": "dga_score_weight", "type": "number", "label": "DGA 评分权重", "default": 0.4},
            {"key": "threat_intel_weight", "type": "number", "label": "威胁情报权重", "default": 0.3},
            {"key": "geoip_risk_weight", "type": "number", "label": "地理风险权重", "default": 0.3},
            {"key": "aggregation_method", "type": "enum", "label": "聚合方法", "options": ["weighted_sum", "max", "bayesian"], "default": "weighted_sum"},
            {"key": "output_field", "type": "string", "label": "输出字段", "default": "risk_score"},
        ],
    },
    "family_classify": {
        "category": "infer",
        "fields": [
            {"key": "endpoint", "type": "string", "label": "服务地址", "required": True, "default": "http://scoring-service:8000"},
            {"key": "model_id", "type": "string", "label": "模型 ID", "default": "multi-cnn-attention"},
            {"key": "top_k", "type": "number", "label": "返回 Top-K 家族", "default": 3},
            {"key": "min_confidence", "type": "number", "label": "最低置信度", "default": 0.3},
            {"key": "timeout_ms", "type": "number", "label": "推理超时 (ms)", "default": 300},
            {"key": "only_dga", "type": "boolean", "label": "仅对 DGA 域名分类", "default": True},
        ],
    },
}

# ── Pydantic Models ────────────────────────────────────────────────


class NodeConfigCreate(BaseModel):
    node_type: str
    name: str
    config: dict = {}
    description: str = ""


class NodeConfigUpdate(BaseModel):
    config: dict | None = None
    name: str | None = None
    description: str | None = None


# ── Schema 查询 ───────────────────────────────────────────────────


@router.get("/node-configs/schemas", dependencies=[Depends(require_viewer)])
async def list_schemas():
    return {"schemas": NODE_CONFIG_SCHEMAS}


@router.get("/node-configs/schemas/{node_type}", dependencies=[Depends(require_viewer)])
async def get_schema(node_type: str):
    schema = NODE_CONFIG_SCHEMAS.get(node_type)
    if not schema:
        raise HTTPException(404, f"Unknown node type: {node_type}")
    return {"node_type": node_type, **schema}


# ── CRUD ──────────────────────────────────────────────────────────


@router.get("/node-configs", dependencies=[Depends(require_viewer)])
async def list_configs(
    node_type: str | None = Query(None),
    category: str | None = Query(None),
    pg: asyncpg.Pool | None = Depends(get_pg_pool),
):
    if not pg:
        return {"configs": []}
    sql = "SELECT * FROM node_configs WHERE 1=1"
    params: list = []
    if node_type:
        params.append(node_type)
        sql += f" AND node_type=${len(params)}"
    if category:
        params.append(category)
        sql += f" AND category=${len(params)}"
    sql += " ORDER BY updated_at DESC"
    rows = await pg.fetch(sql, *params)
    return {
        "configs": [
            {
                "id": r["id"], "node_type": r["node_type"], "category": r["category"],
                "name": r["name"], "config": json.loads(r["config"]) if isinstance(r["config"], str) else (dict(r["config"]) if r["config"] else {}),
                "description": r["description"] or "", "created_at": str(r["created_at"]),
                "updated_at": str(r["updated_at"]),
            }
            for r in rows
        ]
    }


@router.post("/node-configs", dependencies=[Depends(require_admin)])
async def create_config(req: NodeConfigCreate, pg: asyncpg.Pool | None = Depends(get_pg_pool)):
    schema = NODE_CONFIG_SCHEMAS.get(req.node_type)
    if not schema:
        raise HTTPException(400, f"Unknown node type: {req.node_type}")
    if not pg:
        raise HTTPException(503, "Database unavailable")
    try:
        row = await pg.fetchrow(
            "INSERT INTO node_configs (node_type, category, name, config, description) "
            "VALUES ($1, $2, $3, $4::jsonb, $5) RETURNING *",
            req.node_type, schema["category"], req.name, json.dumps(req.config), req.description,
        )
        return {
            "id": row["id"], "node_type": row["node_type"], "category": row["category"],
            "name": row["name"], "config": json.loads(row["config"]) if isinstance(row["config"], str) else (dict(row["config"]) if row["config"] else {}),
            "description": row["description"] or "",
        }
    except asyncpg.UniqueViolationError:
        raise HTTPException(409, f"Config '{req.name}' already exists for {req.node_type}")


@router.get("/node-configs/{config_id}", dependencies=[Depends(require_viewer)])
async def get_config(config_id: int, pg: asyncpg.Pool | None = Depends(get_pg_pool)):
    if not pg:
        raise HTTPException(503, "Database unavailable")
    row = await pg.fetchrow("SELECT * FROM node_configs WHERE id=$1", config_id)
    if not row:
        raise HTTPException(404, "Config not found")
    return {
        "id": row["id"], "node_type": row["node_type"], "category": row["category"],
        "name": row["name"], "config": json.loads(row["config"]) if isinstance(row["config"], str) else (dict(row["config"]) if row["config"] else {}),
        "description": row["description"] or "",
        "created_at": str(row["created_at"]), "updated_at": str(row["updated_at"]),
    }


@router.put("/node-configs/{config_id}", dependencies=[Depends(require_admin)])
async def update_config(config_id: int, req: NodeConfigUpdate, pg: asyncpg.Pool | None = Depends(get_pg_pool)):
    if not pg:
        raise HTTPException(503, "Database unavailable")
    row = await pg.fetchrow("SELECT * FROM node_configs WHERE id=$1", config_id)
    if not row:
        raise HTTPException(404, "Config not found")
    new_name = req.name if req.name is not None else row["name"]
    new_config = json.dumps(req.config) if req.config is not None else (row["config"] if isinstance(row["config"], str) else json.dumps(dict(row["config"]) if row["config"] else {}))
    new_desc = req.description if req.description is not None else (row["description"] or "")
    await pg.execute(
        "UPDATE node_configs SET name=$1, config=$2::jsonb, description=$3, updated_at=NOW() WHERE id=$4",
        new_name, new_config, new_desc, config_id,
    )
    return {"ok": True, "id": config_id}


@router.delete("/node-configs/{config_id}", dependencies=[Depends(require_admin)])
async def delete_config(config_id: int, pg: asyncpg.Pool | None = Depends(get_pg_pool)):
    if not pg:
        raise HTTPException(503, "Database unavailable")
    result = await pg.execute("DELETE FROM node_configs WHERE id=$1", config_id)
    if result == "DELETE 0":
        raise HTTPException(404, "Config not found")
    return {"ok": True}
