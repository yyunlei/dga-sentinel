"""
Agent 监控路由 — /agents/metrics, /agents/exec-history, /agents/a2a-messages
提供 Agent 运行状态、执行历史和 A2A 消息流数据
"""
from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from gateway.middleware.auth import verify_token
from gateway.middleware.rbac import require_analyst
from shared.observability import get_logger

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
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{AGENT_LAYER_URL}/agents")
            resp.raise_for_status()
            data = resp.json()
            agents_raw = data.get("agents", [])
            # agent-layer returns list of strings — convert to metrics format
            agents_metrics = []
            for item in agents_raw:
                if isinstance(item, dict):
                    agents_metrics.append(item)
                elif isinstance(item, str):
                    agents_metrics.append({
                        "name": item,
                        "status": "online",
                        "execCount": 0,
                        "avgLatency": 0.0,
                        "errorRate": 0.0,
                    })
            return {"agents": agents_metrics}
    except Exception:
        raise HTTPException(status_code=503, detail="Agent layer unavailable")


@router.get("/agents/exec-history", dependencies=[Depends(require_analyst)])
async def get_exec_history(limit: int = Query(50, le=200)):
    """获取 Agent 执行历史"""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{AGENT_LAYER_URL}/agents/exec-history", params={"limit": limit})
            if resp.status_code == 404:
                return {"records": []}
            resp.raise_for_status()
            return resp.json()
    except Exception:
        return {"records": []}


@router.get("/agents/a2a-messages", dependencies=[Depends(require_analyst)])
async def get_a2a_messages(limit: int = Query(20, le=100)):
    """获取 A2A 消息流"""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{AGENT_LAYER_URL}/agents/a2a-messages", params={"limit": limit})
            if resp.status_code == 404:
                return {"messages": []}
            resp.raise_for_status()
            return resp.json()
    except Exception:
        return {"messages": []}
