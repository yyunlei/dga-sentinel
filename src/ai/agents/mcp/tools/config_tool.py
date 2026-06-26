"""MCP Tool — 配置管理"""
from __future__ import annotations
import json
import redis.asyncio as aioredis
from shared.config import get_settings
from shared.observability import get_logger

logger = get_logger(__name__)


class ConfigTool:
    """管理阈值、白名单、模型路由等运行时配置"""
    name = "config"
    description = "读写 DGA 检测平台的运行时配置"
    input_schema = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["get", "set", "list"], "description": "Operation type"},
            "key": {"type": "string", "description": "Config key"},
            "value": {"description": "Config value (for set action)"},
        },
        "required": ["action"],
    }

    async def run(self, **kwargs) -> dict:
        action = kwargs.get("action", "list")
        key = kwargs.get("key", "")
        value = kwargs.get("value")
        settings = get_settings()
        try:
            r = aioredis.from_url(settings.redis_url)
            try:
                prefix = "dga:config:"
                if action == "get" and key:
                    raw = await r.get(f"{prefix}{key}")
                    val = json.loads(raw) if raw else None
                    return {"key": key, "value": val}
                elif action == "set" and key:
                    await r.set(f"{prefix}{key}", json.dumps(value))
                    return {"key": key, "value": value, "status": "updated"}
                elif action == "list":
                    keys = []
                    async for k in r.scan_iter(f"{prefix}*"):
                        keys.append(k.decode() if isinstance(k, bytes) else k)
                    return {"keys": [k.removeprefix(prefix) for k in keys]}
                else:
                    return {"error": "Invalid action or missing key"}
            finally:
                await r.aclose()
        except Exception as e:
            logger.error("config_tool_error", error=str(e))
            return {"error": str(e)}
