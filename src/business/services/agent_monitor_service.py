"""
Agent 监控业务编排 — AgentMonitorService。
不依赖 FastAPI；client 通过构造函数注入，可独立单测。

职责：
  get_metrics       — 调用 client 获取原始 agent 列表，将字符串条目转为指标字典格式并组装响应。
  get_exec_history  — 透传 client 的执行历史响应（含静默降级）。
  get_a2a_messages  — 透传 client 的 A2A 消息流响应（含静默降级）。
"""
from __future__ import annotations

from common.observability import get_logger

logger = get_logger(__name__)


class AgentMonitorService:
    """Agent 监控业务编排：client 通过构造函数注入，禁止 import fastapi。"""

    def __init__(self, client) -> None:
        """
        :param client: AgentMonitorClient（或实现相同接口的 fake）
        """
        self._client = client

    async def get_metrics(self) -> dict:
        """获取 Agent 运行状态指标，将原始 agent-layer 响应组装为标准指标格式。

        agent-layer 返回的 agents 字段可能为字符串列表或字典列表：
          - dict 条目：原样保留。
          - str  条目：转换为默认指标结构（status=online，计数/延迟/错误率均为零）。

        :returns: {"agents": [AgentMetrics, ...]}
        :raises:  网络/HTTP 异常原样向上抛出，由 api 层映射为 HTTPException(503)。
        """
        data = await self._client.fetch_metrics()
        agents_raw = data.get("agents", [])
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

    async def get_exec_history(self, limit: int) -> dict:
        """获取 Agent 执行历史。

        :param limit: 最多返回条数（由 api 层 Query 约束，透传至 client）。
        :returns: {"records": [...]}，异常时由 client 静默降级为空列表。
        """
        return await self._client.fetch_exec_history(limit)

    async def get_a2a_messages(self, limit: int) -> dict:
        """获取 A2A 消息流。

        :param limit: 最多返回条数（由 api 层 Query 约束，透传至 client）。
        :returns: {"messages": [...]}，异常时由 client 静默降级为空列表。
        """
        return await self._client.fetch_a2a_messages(limit)
