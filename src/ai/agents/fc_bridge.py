"""
MCPFunctionCallingBridge — MCP 工具自动转换为 LangChain StructuredTool
支持 Agent 通过 LLM Function Calling 自主调用 MCP 工具
"""

from __future__ import annotations

import asyncio
from typing import Any, Type

from pydantic import BaseModel, Field, create_model
from langchain_core.tools import StructuredTool

from agent_layer.mcp.server import MCPServer
from shared.observability import get_logger

logger = get_logger(__name__)


def _schema_to_pydantic(name: str, schema: dict) -> Type[BaseModel]:
    """将 JSON Schema 转换为 Pydantic Model"""
    properties = schema.get("properties", {})
    required = set(schema.get("required", []))
    fields = {}

    type_map = {
        "string": str,
        "integer": int,
        "number": float,
        "boolean": bool,
        "object": dict,
        "array": list,
    }

    for prop_name, prop_schema in properties.items():
        prop_type = type_map.get(prop_schema.get("type", "string"), str)
        description = prop_schema.get("description", "")
        default = prop_schema.get("default")

        if prop_name in required:
            fields[prop_name] = (prop_type, Field(description=description))
        else:
            fields[prop_name] = (prop_type, Field(default=default, description=description))

    model_name = f"{name.title().replace('_', '')}Input"
    return create_model(model_name, **fields)


class MCPFunctionCallingBridge:
    """
    MCP → LangChain Function Calling 桥接器
    将 MCP 工具自动转换为 LangChain StructuredTool，
    支持 LLM bind_tools 自主调用
    """

    def __init__(self, mcp_server: MCPServer, whitelist: set[str] | None = None):
        self.mcp_server = mcp_server
        self.whitelist = whitelist  # None = allow all
        self._tools_cache: list[StructuredTool] | None = None

    def get_langchain_tools(self) -> list[StructuredTool]:
        """将所有 MCP 工具转换为 LangChain StructuredTool"""
        if self._tools_cache is not None:
            return self._tools_cache

        tools = []
        for name in self.mcp_server.list_tools():
            if self.whitelist is not None and name not in self.whitelist:
                continue

            mcp_tool = self.mcp_server.get_tool(name)
            if not mcp_tool:
                continue

            schema = getattr(mcp_tool, "input_schema", {})
            args_schema = _schema_to_pydantic(name, schema)

            # Capture tool reference for closure
            _tool = mcp_tool
            _name = name

            async def _run_async(_t=_tool, **kwargs) -> dict:
                return await _t.run(**kwargs)

            def _run_sync(_t=_tool, **kwargs) -> dict:
                return asyncio.get_event_loop().run_until_complete(_t.run(**kwargs))

            lc_tool = StructuredTool(
                name=name,
                description=getattr(mcp_tool, "description", ""),
                args_schema=args_schema,
                func=_run_sync,
                coroutine=_run_async,
            )
            tools.append(lc_tool)

        self._tools_cache = tools
        logger.info("fc_bridge_tools_loaded", count=len(tools))
        return tools

    def get_tool_by_name(self, name: str) -> StructuredTool | None:
        for tool in self.get_langchain_tools():
            if tool.name == name:
                return tool
        return None

    def is_allowed(self, tool_name: str) -> bool:
        if self.whitelist is None:
            return True
        return tool_name in self.whitelist
