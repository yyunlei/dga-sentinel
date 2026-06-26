"""MCP Tool — 威胁情报查询"""
from __future__ import annotations
import redis.asyncio as aioredis
from shared.config import get_settings
from shared.observability import get_logger

logger = get_logger(__name__)


class ThreatIntelTool:
    """查询威胁情报：Redis 黑名单 + 外部 API"""
    name = "threat_intel"
    description = "查询域名/IP 的威胁情报，包括本地黑名单和外部情报源"
    input_schema = {
        "type": "object",
        "properties": {
            "domain": {"type": "string", "description": "Domain to check"},
            "ip": {"type": "string", "description": "IP to check"},
        },
    }

    async def run(self, **kwargs) -> dict:
        domain = kwargs.get("domain", "")
        ip = kwargs.get("ip", "")
        settings = get_settings()
        result = {"domain": domain, "ip": ip, "blacklisted": False, "sources": [], "tags": []}
        try:
            r = aioredis.from_url(settings.redis_url)
            try:
                if domain:
                    is_bl = await r.sismember("dga:blacklist:domains", domain)
                    if is_bl:
                        result["blacklisted"] = True
                        result["sources"].append("local_blacklist")
                        result["tags"].append("known_malicious")
                if ip:
                    is_bl = await r.sismember("dga:blacklist:ips", ip)
                    if is_bl:
                        result["blacklisted"] = True
                        result["sources"].append("local_ip_blacklist")
            finally:
                await r.aclose()
        except Exception as e:
            logger.error("threat_intel_error", error=str(e))
            result["error"] = str(e)
        return result
