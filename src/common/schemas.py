"""
DGA Platform — 公共 Pydantic 数据模型
所有服务共享的 schema 定义
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field


# ── 枚举 ──────────────────────────────────────────────

class Severity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ModelStatus(str, Enum):
    STAGING = "staging"
    PRODUCTION = "production"
    ARCHIVED = "archived"


class PipelineMode(str, Enum):
    STREAM = "stream"
    BATCH = "batch"


class PipelineStatus(str, Enum):
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"


# ── 评分相关 ──────────────────────────────────────────

class ScoreRequest(BaseModel):
    domains: list[str] = Field(..., min_length=1, max_length=1000, description="域名列表")
    tenant_id: str = "default"


class ScoreResult(BaseModel):
    domain: str
    score: float = Field(..., ge=0.0, le=1.0)
    is_dga: bool
    family: str | None = None
    family_confidence: float | None = None
    model_version: str = ""
    cached: bool = False


class ScoreResponse(BaseModel):
    trace_id: str = Field(default_factory=lambda: uuid4().hex)
    results: list[ScoreResult]
    latency_ms: float = 0.0


# ── 告警事件 ──────────────────────────────────────────

class DGAEvent(BaseModel):
    """dag→agents Kafka 告警(topic: dga-alerts)与事件 sink 的规范契约。

    DAG 引擎(KafkaSinkNode)序列化此模型发布告警,
    Agent 层(alert consumer)用 model_validate 校验后消费,
    两端共享同一显式 schema,禁止裸 dict 跨越此边界。
    """

    trace_id: str = Field(default_factory=lambda: uuid4().hex)
    event_id: str = Field(default_factory=lambda: uuid4().hex)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    domain: str
    src_ip: str = ""
    query_type: str = "A"
    score: float = 0.0
    is_dga: bool = False
    family: str | None = None
    family_confidence: float | None = None
    model_version: str = ""
    pipeline_id: str = ""
    features: dict = Field(default_factory=dict)
    rules_applied: list[str] = Field(default_factory=list)
    tenant_id: str = "default"
    severity: Severity = Severity.LOW
