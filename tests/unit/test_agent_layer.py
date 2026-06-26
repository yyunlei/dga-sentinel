"""
M1 单元测试 — BaseAgent 状态机编译、A2A 消息传递、MCP 工具 schema 校验
"""

from __future__ import annotations

import asyncio
import json

import pytest

from ai.agents.a2a.protocol import A2AMessage
from ai.agents.a2a.bus import AgentBus
from ai.agents.base_agent import BaseAgent, AgentState


# --- Concrete test agent ---

class DummyAgent(BaseAgent):
    name = "dummy"

    async def perceive(self, state: AgentState) -> AgentState:
        state["context"] = {"received": state.get("input_data", {})}
        return state

    async def plan(self, state: AgentState) -> AgentState:
        state["plan"] = ["step1", "step2"]
        return state

    async def act(self, state: AgentState) -> AgentState:
        state["tool_results"] = [{"tool": "test", "result": "ok"}]
        return state

    async def reflect(self, state: AgentState) -> AgentState:
        state["confidence"] = 0.95
        state["reflection"] = "looks good"
        return state

    async def format_output(self, state: AgentState) -> AgentState:
        state["output"] = {"status": "done", "confidence": state.get("confidence", 0)}
        return state


# --- T021: BaseAgent state machine ---

class TestBaseAgent:
    def test_graph_compiles(self):
        agent = DummyAgent()
        assert agent.compiled is not None

    @pytest.mark.asyncio
    async def test_full_lifecycle(self):
        agent = DummyAgent()
        result = await agent.run({"domain": "test.com"}, trace_id="t-001")
        assert result["output"]["status"] == "done"
        assert result["confidence"] == 0.95
        assert result["agent_name"] == "dummy"
        assert result["duration_ms"] >= 0

    @pytest.mark.asyncio
    async def test_error_propagation(self):
        class FailAgent(BaseAgent):
            name = "fail"
            async def perceive(self, state):
                raise ValueError("test error")
            async def plan(self, state):
                return state
            async def act(self, state):
                return state
            async def reflect(self, state):
                return state
            async def format_output(self, state):
                state["output"] = {}
                return state

        agent = FailAgent()
        result = await agent.run({})
        assert result.get("error") == "test error"


# --- T023: A2A message passing ---

class TestA2AProtocol:
    def test_message_serialization(self):
        msg = A2AMessage(from_agent="a", to_agent="b", action="test", payload={"k": "v"})
        json_str = msg.to_json()
        restored = A2AMessage.from_json(json_str)
        assert restored.from_agent == "a"
        assert restored.to_agent == "b"
        assert restored.payload == {"k": "v"}

    def test_reply(self):
        msg = A2AMessage(from_agent="a", to_agent="b", action="query")
        reply = msg.reply({"result": 42})
        assert reply.from_agent == "b"
        assert reply.to_agent == "a"
        assert reply.action == "query_response"
        assert reply.reply_to == msg.msg_id


class TestAgentBus:
    @pytest.mark.asyncio
    async def test_local_handler(self):
        bus = AgentBus()
        received = []

        async def handler(msg: A2AMessage):
            received.append(msg)

        bus.register_handler("target", handler)
        await bus.send(A2AMessage(from_agent="src", to_agent="target", action="ping"))
        assert len(received) == 1
        assert received[0].action == "ping"

    @pytest.mark.asyncio
    async def test_no_handler_warning(self):
        bus = AgentBus()
        # Should not raise
        await bus.send(A2AMessage(from_agent="src", to_agent="nonexistent", action="ping"))


# --- MCP tool schema validation ---

class TestMCPToolSchemas:
    """Verify all 10 MCP tools have proper name, description, input_schema."""

    TOOL_CLASSES = []

    @classmethod
    def setup_class(cls):
        from ai.agents.mcp.tools.es_query import ESQueryTool
        from ai.agents.mcp.tools.threat_intel import ThreatIntelTool
        from ai.agents.mcp.tools.model_info import ModelInfoTool
        from ai.agents.mcp.tools.config_tool import ConfigTool
        from ai.agents.mcp.tools.starrocks_query import StarRocksQueryTool
        from ai.agents.mcp.tools.redis_query import RedisQueryTool
        from ai.agents.mcp.tools.dns_resolve import DNSResolveTool
        from ai.agents.mcp.tools.whois_lookup import WhoisLookupTool
        from ai.agents.mcp.tools.geoip_lookup import GeoIPLookupTool
        from ai.agents.mcp.tools.report_generate import ReportGenerateTool

        cls.TOOL_CLASSES = [
            ESQueryTool, ThreatIntelTool, ModelInfoTool, ConfigTool,
            StarRocksQueryTool, RedisQueryTool, DNSResolveTool,
            WhoisLookupTool, GeoIPLookupTool, ReportGenerateTool,
        ]

    def test_all_10_tools_exist(self):
        assert len(self.TOOL_CLASSES) == 10

    def test_tools_have_name(self):
        for cls in self.TOOL_CLASSES:
            tool = cls()
            assert hasattr(tool, "name"), f"{cls.__name__} missing 'name'"
            assert isinstance(tool.name, str) and len(tool.name) > 0

    def test_tools_have_description(self):
        for cls in self.TOOL_CLASSES:
            tool = cls()
            assert hasattr(tool, "description"), f"{cls.__name__} missing 'description'"
            assert isinstance(tool.description, str) and len(tool.description) > 0

    def test_tools_have_input_schema(self):
        for cls in self.TOOL_CLASSES:
            tool = cls()
            assert hasattr(tool, "input_schema"), f"{cls.__name__} missing 'input_schema'"
            schema = tool.input_schema
            assert isinstance(schema, dict)
            assert schema.get("type") == "object"
            assert "properties" in schema

    def test_tools_have_run_method(self):
        for cls in self.TOOL_CLASSES:
            tool = cls()
            assert hasattr(tool, "run"), f"{cls.__name__} missing 'run' method"
            assert asyncio.iscoroutinefunction(tool.run)

    def test_unique_tool_names(self):
        names = [cls().name for cls in self.TOOL_CLASSES]
        assert len(names) == len(set(names)), f"Duplicate tool names: {names}"


# --- MCP Server ---

class TestMCPServer:
    def test_server_registers_all_tools(self):
        from ai.agents.mcp.server import MCPServer
        server = MCPServer()
        server.register_defaults()
        assert len(server.list_tools()) == 10

    def test_server_get_schema(self):
        from ai.agents.mcp.server import MCPServer
        server = MCPServer()
        server.register_defaults()
        schema = server.get_tool_schema("es_query")
        assert schema is not None
        assert schema["name"] == "es_query"
        assert "input_schema" in schema

    def test_server_unknown_tool(self):
        from ai.agents.mcp.server import MCPServer
        server = MCPServer()
        assert server.get_tool_schema("nonexistent") is None


# --- Orchestrator ---

class TestOrchestrator:
    def test_register_and_list(self):
        from ai.agents.orchestrator import AgentOrchestrator
        bus = AgentBus()
        orch = AgentOrchestrator(bus)
        agent = DummyAgent(bus=bus)
        orch.register(agent)
        assert "dummy" in orch.list_agents()

    @pytest.mark.asyncio
    async def test_dispatch(self):
        from ai.agents.orchestrator import AgentOrchestrator
        bus = AgentBus()
        orch = AgentOrchestrator(bus)
        orch.register(DummyAgent(bus=bus))
        result = await orch.dispatch("dummy", {"test": True})
        assert result["output"]["status"] == "done"

    @pytest.mark.asyncio
    async def test_dispatch_unknown_agent(self):
        from ai.agents.orchestrator import AgentOrchestrator
        bus = AgentBus()
        orch = AgentOrchestrator(bus)
        with pytest.raises(KeyError):
            await orch.dispatch("nonexistent", {})
