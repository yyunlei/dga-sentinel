"""
T088 集成测试 — 告警 → TriageAgent → ExplainAgent + ThreatIntelAgent → ResponseAgent 全链路
验证 Agent 管道各阶段的交互:
  - 各 Agent 可独立实例化并运行
  - A2A Bus 消息传递正确
  - 全链路 triage → explain + threat_intel → response
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai.agents.a2a.bus import AgentBus
from ai.agents.a2a.protocol import A2AMessage


# ── Fixtures ──────────────────────────────────────────────

SAMPLE_ALERT = {
    "domain": "xk3jf9a2.evil.com",
    "src_ip": "192.168.1.100",
    "score": 0.96,
    "family": "conficker",
    "@timestamp": "2025-06-01T12:00:00Z",
}


@pytest.fixture
def mock_bus():
    bus = AgentBus(redis_client=None)
    bus.send = AsyncMock()
    return bus


@pytest.fixture
def mock_es_tool():
    tool = AsyncMock()
    tool.run = AsyncMock(return_value={
        "total": 3,
        "hits": [
            {"domain": "abc.evil.com", "score": 0.91},
            {"domain": "def.evil.com", "score": 0.88},
            {"domain": "ghi.evil.com", "score": 0.85},
        ],
    })
    return tool


@pytest.fixture
def mock_threat_intel_tool():
    tool = MagicMock()
    tool.run = AsyncMock(return_value={
        "blacklisted": True,
        "tags": ["botnet", "c2"],
        "sources": ["alienvault"],
    })
    # Make isinstance check work
    from ai.agents.mcp.tools.threat_intel import ThreatIntelTool
    tool.__class__ = ThreatIntelTool
    return tool


# ── TriageAgent Tests ─────────────────────────────────────

class TestTriageAgent:

    @patch("agent_layer.agents.triage_agent.ESQueryTool")
    def test_triage_instantiation(self, mock_es_cls, mock_bus, mock_es_tool):
        mock_es_cls.return_value = mock_es_tool
        from ai.agents.agents.triage_agent import TriageAgent
        agent = TriageAgent(bus=mock_bus)
        assert agent.name == "triage"
        assert agent.bus is mock_bus

    @patch("agent_layer.agents.triage_agent.ESQueryTool")
    async def test_triage_perceive_extracts_context(self, mock_es_cls, mock_bus, mock_es_tool):
        mock_es_cls.return_value = mock_es_tool
        from ai.agents.agents.triage_agent import TriageAgent
        agent = TriageAgent(bus=mock_bus)
        state = {"input_data": SAMPLE_ALERT}
        result = await agent.perceive(state)
        assert result["context"]["domain"] == "xk3jf9a2.evil.com"
        assert result["context"]["score"] == 0.96

    @patch("agent_layer.agents.triage_agent.ESQueryTool")
    async def test_triage_reflect_critical_severity(self, mock_es_cls, mock_bus, mock_es_tool):
        mock_es_cls.return_value = mock_es_tool
        from ai.agents.agents.triage_agent import TriageAgent
        agent = TriageAgent(bus=mock_bus)
        state = {
            "context": {"score": 0.96, "src_ip": "192.168.1.100"},
            "tool_results": [{"total": 6, "hits": []}],
        }
        result = await agent.reflect(state)
        assert result["reflection"] == "CRITICAL"
        assert result["confidence"] == 0.95


# ── ExplainAgent Tests ────────────────────────────────────

class TestExplainAgent:

    @patch("agent_layer.agents.explain_agent.get_settings")
    async def test_explain_perceive(self, mock_settings, mock_bus):
        mock_settings.return_value = MagicMock(deepseek_api_key="")
        from ai.agents.agents.explain_agent import ExplainAgent
        agent = ExplainAgent(bus=mock_bus)
        state = {"input_data": SAMPLE_ALERT}
        result = await agent.perceive(state)
        assert result["context"]["domain"] == "xk3jf9a2.evil.com"
        assert result["context"]["family"] == "conficker"

    @patch("agent_layer.agents.explain_agent.get_settings")
    async def test_explain_plan_has_four_dimensions(self, mock_settings, mock_bus):
        mock_settings.return_value = MagicMock(deepseek_api_key="")
        from ai.agents.agents.explain_agent import ExplainAgent
        agent = ExplainAgent(bus=mock_bus)
        state = {"input_data": SAMPLE_ALERT}
        result = await agent.plan(state)
        assert len(result["plan"]) == 4


# ── ThreatIntelAgent Tests ───────────────────────────────

class TestThreatIntelAgent:

    @patch("agent_layer.agents.threat_intel_agent.ThreatIntelTool")
    def test_threat_intel_instantiation(self, mock_tool_cls, mock_bus, mock_threat_intel_tool):
        mock_tool_cls.return_value = mock_threat_intel_tool
        from ai.agents.agents.threat_intel_agent import ThreatIntelAgent
        agent = ThreatIntelAgent(bus=mock_bus)
        assert agent.name == "threat_intel"

    async def test_threat_intel_perceive_extracts_domain_ip(self, mock_bus):
        from ai.agents.agents.threat_intel_agent import ThreatIntelAgent
        agent = ThreatIntelAgent.__new__(ThreatIntelAgent)
        agent.bus = mock_bus
        agent.tools = []
        state = {"input_data": {"domain": "evil.com", "ip": "1.2.3.4"}}
        result = await agent.perceive(state)
        assert result["context"]["domain"] == "evil.com"
        assert result["context"]["ip"] == "1.2.3.4"


# ── ResponseAgent Tests ──────────────────────────────────

class TestResponseAgent:

    def test_response_instantiation(self, mock_bus):
        from ai.agents.agents.response_agent import ResponseAgent
        agent = ResponseAgent(bus=mock_bus)
        assert agent.name == "response"

    async def test_response_plan_critical(self, mock_bus):
        from ai.agents.agents.response_agent import ResponseAgent
        agent = ResponseAgent(bus=mock_bus)
        state = {"context": {"severity": "CRITICAL", "domain": "evil.com", "src_ip": "1.2.3.4"}}
        result = await agent.plan(state)
        assert "block_dns" in result["plan"]
        assert "isolate_host" in result["plan"]
        assert "create_incident" in result["plan"]
        assert "log_event" in result["plan"]

    async def test_response_plan_low(self, mock_bus):
        from ai.agents.agents.response_agent import ResponseAgent
        agent = ResponseAgent(bus=mock_bus)
        state = {"context": {"severity": "LOW", "domain": "ok.com", "src_ip": "10.0.0.1"}}
        result = await agent.plan(state)
        assert result["plan"] == ["log_event"]


# ── Full Pipeline Test ────────────────────────────────────

class TestFullPipeline:
    """Triage → (ExplainAgent + ThreatIntelAgent) → ResponseAgent"""

    @patch("agent_layer.agents.triage_agent.ESQueryTool")
    async def test_triage_sends_a2a_on_critical(self, mock_es_cls, mock_bus, mock_es_tool):
        """TriageAgent should send A2A messages to threat_intel and explain for CRITICAL alerts."""
        mock_es_cls.return_value = mock_es_tool
        from ai.agents.agents.triage_agent import TriageAgent
        agent = TriageAgent(bus=mock_bus)

        # Manually walk through lifecycle to avoid LLM calls
        state = {"input_data": SAMPLE_ALERT, "trace_id": "trace-001"}
        state = await agent.perceive(state)
        state = await agent.plan(state)
        # Skip act (needs ES), inject mock results
        state["tool_results"] = [{"total": 6, "hits": []}]
        state = await agent.reflect(state)
        state = await agent.format_output(state)

        assert state["reflection"] == "CRITICAL"
        # Bus.send should have been called for threat_intel and explain
        assert mock_bus.send.call_count == 2
        calls = mock_bus.send.call_args_list
        to_agents = {call.args[0].to_agent for call in calls}
        assert "threat_intel" in to_agents
        assert "explain" in to_agents

    async def test_response_generates_actions_for_critical(self, mock_bus):
        """ResponseAgent should generate 4 actions for CRITICAL severity."""
        from ai.agents.agents.response_agent import ResponseAgent
        agent = ResponseAgent(bus=mock_bus)

        state = {
            "input_data": {
                "severity": "CRITICAL",
                "domain": "xk3jf9a2.evil.com",
                "src_ip": "192.168.1.100",
                "family": "conficker",
            },
        }
        state = await agent.perceive(state)
        state = await agent.plan(state)

        # Patch RAG SOP lookup to avoid ES
        with patch.object(agent, "_get_sop_context", new_callable=AsyncMock, return_value=""):
            state = await agent.act(state)

        actions = state["tool_results"][0]["actions"]
        action_types = {a["type"] for a in actions}
        assert action_types == {"block_dns", "isolate_host", "create_incident", "log_event"}
