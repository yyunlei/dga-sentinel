"""MCP Tool — Redis 查询"""

from __future__ import annotations

from common.config import get_settings
from common.observability import get_logger

logger = get_logger(__name__)


class RedisQueryTool:
    """Query Redis key-value store."""

    name = "redis_query"
    description = "Query Redis key-value store"

    input_schema: dict = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["get", "keys", "smembers", "hgetall", "ttl"],
            },
            "key": {"type": "string"},
        },
        "required": ["operation", "key"],
    }

    async def run(self, **kwargs) -> dict:
        operation: str = kwargs["operation"]
        key: str = kwargs["key"]
        try:
            import redis.asyncio as aioredis

            settings = get_settings()
            r = aioredis.from_url(settings.redis_url, decode_responses=True)
            try:
                if operation == "get":
                    value = await r.get(key)
                elif operation == "keys":
                    value = await r.keys(key)
                elif operation == "smembers":
                    value = await r.smembers(key)
                    value = list(value) if value else []
                elif operation == "hgetall":
                    value = await r.hgetall(key)
                elif operation == "ttl":
                    value = await r.ttl(key)
                else:
                    return {"error": f"Unsupported operation: {operation}"}
            finally:
                await r.aclose()

            return {"key": key, "operation": operation, "value": value}
        except Exception as exc:
            logger.error("redis_query_failed", error=str(exc))
            return {"error": str(exc)}
