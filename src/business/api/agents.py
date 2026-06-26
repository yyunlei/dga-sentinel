"""
Agent 监控路由 — /agents/metrics, /agents/exec-history, /agents/a2a-messages
提供 Agent 运行状态、执行历史和 A2A 消息流数据
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from business.middleware.auth import verify_token
from business.middleware.rbac import require_analyst
from business.repositories.agent_client import AgentMonitorClient
from business.services.agent_monitor_service import AgentMonitorService
from common.observability import get_logger

router = APIRouter()
logger = get_logger(__name__)

import os

AGENT_LAYER_URL = os.environ.get("AGENT_LAYER_URL", "http://agent-layer:8002")


class AgentMetrics(BaseModel):
    name: str
    status: str
    execCount: int
    avgLatency: float
    errorRate: float


class ExecRecord(BaseModel):
    timestamp: str
    agent: str
    action: str
    duration_ms: int
    status: str
    trace_id: str


class A2AMessage(BaseModel):
    timestamp: str
    from_agent: str
    to_agent: str
    message: str


@router.get("/agents/metrics", dependencies=[Depends(require_analyst)])
async def get_agent_metrics():
    """获取 Agent 运行状态指标"""
    client = AgentMonitorClient(AGENT_LAYER_URL)
    svc = AgentMonitorService(client)
    try:
        return await svc.get_metrics()
    except Exception:
        raise HTTPException(status_code=503, detail="Agent layer unavailable")


@router.get("/agents/exec-history", dependencies=[Depends(require_analyst)])
async def get_exec_history(limit: int = Query(50, le=200)):
    """获取 Agent 执行历史"""
    client = AgentMonitorClient(AGENT_LAYER_URL)
    svc = AgentMonitorService(client)
    return await svc.get_exec_history(limit)


@router.get("/agents/a2a-messages", dependencies=[Depends(require_analyst)])
async def get_a2a_messages(limit: int = Query(20, le=100)):
    """获取 A2A 消息流"""
    client = AgentMonitorClient(AGENT_LAYER_URL)
    svc = AgentMonitorService(client)
    return await svc.get_a2a_messages(limit)
