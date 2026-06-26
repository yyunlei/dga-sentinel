"""
M2 测试 — FC Bridge 转换正确性、白名单拒绝、安全防护
"""

from __future__ import annotations

import pytest

from ai.agents.mcp.server import MCPServer
from ai.agents.fc_bridge import MCPFunctionCallingBridge, _schema_to_pydantic
from ai.agents.fc_security import FCSecurityGuard


@pytest.fixture
def mcp_server():
    server = MCPServer()
    server.register_defaults()
    return server


@pytest.fixture
def bridge(mcp_server):
    return MCPFunctionCallingBridge(mcp_server)


@pytest.fixture
def restricted_bridge(mcp_server):
    return MCPFunctionCallingBridge(mcp_server, whitelist={"es_query", "threat_intel"})


# --- T042: Bridge conversion ---

class TestFCBridge:
    def test_get_langchain_tools_returns_10(self, bridge):
        tools = bridge.get_langchain_tools()
        assert len(tools) == 10

    def test_tools_have_name_and_description(self, bridge):
        for tool in bridge.get_langchain_tools():
            assert tool.name
            assert tool.description

    def test_tools_have_args_schema(self, bridge):
        for tool in bridge.get_langchain_tools():
            assert tool.args_schema is not None

    def test_whitelist_filters_tools(self, restricted_bridge):
        tools = restricted_bridge.get_langchain_tools()
        names = {t.name for t in tools}
        assert names == {"es_query", "threat_intel"}

    def test_is_allowed(self, restricted_bridge):
        assert restricted_bridge.is_allowed("es_query") is True
        assert restricted_bridge.is_allowed("config") is False

    def test_get_tool_by_name(self, bridge):
        tool = bridge.get_tool_by_name("es_query")
        assert tool is not None
        assert tool.name == "es_query"

    def test_get_tool_by_name_missing(self, bridge):
        assert bridge.get_tool_by_name("nonexistent") is None


# --- Schema to Pydantic ---

class TestSchemaToPydantic:
    def test_basic_schema(self):
        schema = {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "limit": {"type": "integer", "default": 10},
            },
            "required": ["query"],
        }
        model = _schema_to_pydantic("test", schema)
        assert model.__name__ == "TestInput"
        # Required field
        fields = model.model_fields
        assert "query" in fields
        assert "limit" in fields

    def test_empty_schema(self):
        model = _schema_to_pydantic("empty", {"type": "object", "properties": {}})
        assert model is not None


# --- T045: Security guard ---

class TestFCSecurity:
    def test_whitelist_allows(self):
        guard = FCSecurityGuard()
        assert guard.check_whitelist("es_query") is True

    def test_whitelist_rejects(self):
        guard = FCSecurityGuard()
        assert guard.check_whitelist("dangerous_tool") is False

    def test_rate_limit_allows(self):
        guard = FCSecurityGuard(rate_limit=5)
        for _ in range(5):
            assert guard.check_rate_limit("agent1") is True

    def test_rate_limit_blocks(self):
        guard = FCSecurityGuard(rate_limit=2)
        assert guard.check_rate_limit("agent2") is True
        assert guard.check_rate_limit("agent2") is True
        assert guard.check_rate_limit("agent2") is False

    async def test_validate_and_log_whitelist_reject(self):
        guard = FCSecurityGuard()
        ok, msg = await guard.validate_and_log("agent", "bad_tool", {})
        assert ok is False
        assert "whitelist" in msg

    async def test_validate_and_log_rate_limit_reject(self):
        guard = FCSecurityGuard(rate_limit=1)
        ok1, _ = await guard.validate_and_log("agent", "es_query", {})
        assert ok1 is True
        ok2, msg = await guard.validate_and_log("agent", "es_query", {})
        assert ok2 is False
        assert "Rate limit" in msg
