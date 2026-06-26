"""
MCP Server — Model Context Protocol 工具服务
为 Agent 提供统一的工具接口
GET /tools — 列出所有工具
GET /tools/{name}/schema — 获取工具 JSON Schema
POST /tools/{name}/run — 执行工具
"""

from __future__ import annotations

from typing import Any

from shared.observability import get_logger

logger = get_logger(__name__)


class MCPServer:
    """MCP 工具服务器：注册和管理 Agent 可用的工具"""

    def __init__(self):
        self._tools: dict[str, Any] = {}

    def register_tool(self, name: str, tool: Any) -> None:
        self._tools[name] = tool
        logger.info("mcp_tool_registered", tool=name)

    def get_tool(self, name: str) -> Any:
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        return list(self._tools.keys())

    def get_tool_schema(self, name: str) -> dict | None:
        tool = self._tools.get(name)
        if not tool:
            return None
        return {
            "name": getattr(tool, "name", name),
            "description": getattr(tool, "description", ""),
            "input_schema": getattr(tool, "input_schema", {}),
        }

    def register_defaults(self) -> None:
        """注册全部 10 个工具"""
        from agent_layer.mcp.tools.es_query import ESQueryTool
        from agent_layer.mcp.tools.model_info import ModelInfoTool
        from agent_layer.mcp.tools.config_tool import ConfigTool
        from agent_layer.mcp.tools.threat_intel import ThreatIntelTool
        from agent_layer.mcp.tools.starrocks_query import StarRocksQueryTool
        from agent_layer.mcp.tools.redis_query import RedisQueryTool
        from agent_layer.mcp.tools.dns_resolve import DNSResolveTool
        from agent_layer.mcp.tools.whois_lookup import WhoisLookupTool
        from agent_layer.mcp.tools.geoip_lookup import GeoIPLookupTool
        from agent_layer.mcp.tools.report_generate import ReportGenerateTool

        self.register_tool("es_query", ESQueryTool())
        self.register_tool("model_info", ModelInfoTool())
        self.register_tool("config", ConfigTool())
        self.register_tool("threat_intel", ThreatIntelTool())
        self.register_tool("starrocks_query", StarRocksQueryTool())
        self.register_tool("redis_query", RedisQueryTool())
        self.register_tool("dns_resolve", DNSResolveTool())
        self.register_tool("whois_lookup", WhoisLookupTool())
        self.register_tool("geoip_lookup", GeoIPLookupTool())
        self.register_tool("report_generate", ReportGenerateTool())

    def create_app(self) -> Any:
        """创建 FastAPI 应用"""
        import os
        from fastapi import FastAPI, HTTPException, Request

        app = FastAPI(title="MCP Tool Server", version="2.0")
        mcp_api_key = os.environ.get("MCP_API_KEY", "")

        @app.middleware("http")
        async def check_api_key(request: Request, call_next):
            if request.url.path == "/health":
                return await call_next(request)
            if mcp_api_key:
                key = request.headers.get("X-API-Key", "")
                if key != mcp_api_key:
                    from starlette.responses import JSONResponse
                    return JSONResponse(status_code=403, content={"detail": "Invalid API key"})
            return await call_next(request)

        @app.get("/health")
        async def health():
            return {"status": "ok", "tool_count": len(self._tools)}

        @app.get("/tools")
        async def list_tools_endpoint():
            tools = []
            for name in self._tools:
                schema = self.get_tool_schema(name)
                tools.append(schema)
            return {"tools": tools}

        @app.get("/tools/{name}/schema")
        async def get_schema(name: str):
            schema = self.get_tool_schema(name)
            if not schema:
                raise HTTPException(404, f"Tool '{name}' not found")
            return schema

        @app.post("/tools/{name}/run")
        async def run_tool(name: str, params: dict = {}):
            tool = self.get_tool(name)
            if not tool:
                raise HTTPException(404, f"Tool '{name}' not found")
            try:
                result = await tool.run(**params)
                return {"tool": name, "result": result}
            except Exception as e:
                logger.error("mcp_tool_error", tool=name, error=str(e))
                raise HTTPException(500, f"Tool execution failed: {e}")

        return app


def build_app() -> Any:
    """供 uvicorn 调用的工厂函数"""
    from shared.observability import setup_logging
    setup_logging()
    server = MCPServer()
    server.register_defaults()
    return server.create_app()
