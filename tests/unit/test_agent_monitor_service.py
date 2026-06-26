"""
AgentMonitorService 单测：fake AgentMonitorClient，秒级运行，无需 Docker。

覆盖：
  1. get_metrics() — 字符串 agents 正确转为指标字典格式
  2. get_metrics() — 字典 agents 原样保留；混合列表两种类型均正确处理
  3. get_metrics() — client 抛出异常时向上传播（api 层负责映射 HTTPException）
  4. get_exec_history(limit) — limit 参数正确透传给 client，响应原样返回
  5. get_a2a_messages(limit) — limit 参数正确透传给 client，响应原样返回
"""
from __future__ import annotations

import pytest

from business.services.agent_monitor_service import AgentMonitorService


# ---------------------------------------------------------------------------
# Fake client
# ---------------------------------------------------------------------------

class FakeAgentMonitorClient:
    """模拟 AgentMonitorClient 的三个方法。"""

    def __init__(
        self,
        metrics_resp=None,
        exec_history_resp=None,
        a2a_messages_resp=None,
        metrics_error: Exception | None = None,
    ) -> None:
        self._metrics_resp = metrics_resp or {"agents": []}
        self._exec_history_resp = exec_history_resp or {"records": []}
        self._a2a_messages_resp = a2a_messages_resp or {"messages": []}
        self._metrics_error = metrics_error
        # 记录调用参数
        self.exec_history_calls: list[int] = []
        self.a2a_messages_calls: list[int] = []

    async def fetch_metrics(self) -> dict:
        if self._metrics_error is not None:
            raise self._metrics_error
        return self._metrics_resp

    async def fetch_exec_history(self, limit: int) -> dict:
        self.exec_history_calls.append(limit)
        return self._exec_history_resp

    async def fetch_a2a_messages(self, limit: int) -> dict:
        self.a2a_messages_calls.append(limit)
        return self._a2a_messages_resp


# ---------------------------------------------------------------------------
# Test 1: 字符串 agents → 转为指标字典
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_metrics_converts_string_agents():
    """字符串类型的 agent 名称应被转为含默认指标值的字典。"""
    fake = FakeAgentMonitorClient(
        metrics_resp={"agents": ["triage", "threat-intel", "explain"]}
    )
    svc = AgentMonitorService(fake)
    result = await svc.get_metrics()

    assert "agents" in result
    agents = result["agents"]
    assert len(agents) == 3

    assert agents[0] == {
        "name": "triage",
        "status": "online",
        "execCount": 0,
        "avgLatency": 0.0,
        "errorRate": 0.0,
    }
    assert agents[1]["name"] == "threat-intel"
    assert agents[2]["name"] == "explain"
    # 所有转换后的条目 status 均为 online
    for a in agents:
        assert a["status"] == "online"
        assert a["execCount"] == 0


# ---------------------------------------------------------------------------
# Test 2: 混合 agents（dict + str）→ 正确处理两种类型
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_metrics_handles_mixed_agents():
    """dict 条目原样保留；str 条目转为默认指标结构；混合列表两类均正确。"""
    dict_agent = {
        "name": "response",
        "status": "busy",
        "execCount": 42,
        "avgLatency": 1.5,
        "errorRate": 0.02,
    }
    fake = FakeAgentMonitorClient(
        metrics_resp={"agents": [dict_agent, "explain"]}
    )
    svc = AgentMonitorService(fake)
    result = await svc.get_metrics()

    agents = result["agents"]
    assert len(agents) == 2
    # dict 条目原样保留
    assert agents[0] == dict_agent
    # str 条目转为默认结构
    assert agents[1] == {
        "name": "explain",
        "status": "online",
        "execCount": 0,
        "avgLatency": 0.0,
        "errorRate": 0.0,
    }


# ---------------------------------------------------------------------------
# Test 3: get_metrics() client 抛异常 → 异常向上传播
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_metrics_propagates_client_exception():
    """client.fetch_metrics() 抛出异常时，service 不吞并，原样向上传播。"""
    fake = FakeAgentMonitorClient(
        metrics_error=ConnectionError("agent-layer unavailable")
    )
    svc = AgentMonitorService(fake)

    with pytest.raises(ConnectionError, match="agent-layer unavailable"):
        await svc.get_metrics()


# ---------------------------------------------------------------------------
# Test 4: get_exec_history(limit) → limit 透传，响应原样返回
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_exec_history_forwards_limit_and_returns_response():
    """limit 参数应透传给 client；响应 dict 原样返回。"""
    records = [
        {
            "timestamp": "2024-01-01T00:00:00Z",
            "agent": "triage",
            "action": "classify",
            "duration_ms": 120,
            "status": "success",
            "trace_id": "abc123",
        }
    ]
    fake = FakeAgentMonitorClient(exec_history_resp={"records": records})
    svc = AgentMonitorService(fake)

    result = await svc.get_exec_history(limit=25)

    # limit 参数正确透传
    assert fake.exec_history_calls == [25]
    # 响应内容原样返回
    assert result == {"records": records}


# ---------------------------------------------------------------------------
# Test 5: get_a2a_messages(limit) → limit 透传，响应原样返回
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_a2a_messages_forwards_limit_and_returns_response():
    """limit 参数应透传给 client；响应 dict 原样返回。"""
    messages = [
        {
            "timestamp": "2024-01-01T00:01:00Z",
            "from_agent": "triage",
            "to_agent": "threat-intel",
            "message": "high severity domain detected",
        }
    ]
    fake = FakeAgentMonitorClient(a2a_messages_resp={"messages": messages})
    svc = AgentMonitorService(fake)

    result = await svc.get_a2a_messages(limit=10)

    # limit 参数正确透传
    assert fake.a2a_messages_calls == [10]
    # 响应内容原样返回
    assert result == {"messages": messages}
