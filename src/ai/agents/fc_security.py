"""
Function Calling 安全防护
- 工具白名单校验
- 调用频率限制 (Redis 计数器)
- 审计日志写入 PG audit_log
"""

from __future__ import annotations

import time
from typing import Any

from common.config import get_settings
from common.observability import get_logger

logger = get_logger(__name__)

# 默认工具白名单
DEFAULT_WHITELIST = {
    "es_query", "threat_intel", "model_info", "config",
    "starrocks_query", "redis_query", "dns_resolve",
    "whois_lookup", "geoip_lookup", "report_generate",
}

# 每分钟最大调用次数
DEFAULT_RATE_LIMIT = 60


class FCSecurityGuard:
    """Function Calling 安全防护"""

    def __init__(
        self,
        whitelist: set[str] | None = None,
        rate_limit: int = DEFAULT_RATE_LIMIT,
    ):
        self.whitelist = whitelist or DEFAULT_WHITELIST
        self.rate_limit = rate_limit
        self._call_counts: dict[str, list[float]] = {}

    def check_whitelist(self, tool_name: str) -> bool:
        allowed = tool_name in self.whitelist
        if not allowed:
            logger.warning("fc_whitelist_rejected", tool=tool_name)
        return allowed

    def check_rate_limit(self, agent_name: str) -> bool:
        now = time.time()
        window = 60.0
        calls = self._call_counts.get(agent_name, [])
        # Remove expired entries
        calls = [t for t in calls if now - t < window]
        self._call_counts[agent_name] = calls

        if len(calls) >= self.rate_limit:
            logger.warning("fc_rate_limited", agent=agent_name, count=len(calls))
            return False
        calls.append(now)
        return True

    async def check_rate_limit_redis(self, agent_name: str) -> bool:
        """Redis-based rate limiting for distributed deployments"""
        try:
            import redis.asyncio as aioredis
            settings = get_settings()
            r = aioredis.from_url(settings.redis_url)
            try:
                key = f"fc:rate:{agent_name}"
                count = await r.incr(key)
                if count == 1:
                    await r.expire(key, 60)
                if count > self.rate_limit:
                    logger.warning("fc_rate_limited_redis", agent=agent_name, count=count)
                    return False
                return True
            finally:
                await r.aclose()
        except Exception:
            # Fallback to in-memory
            return self.check_rate_limit(agent_name)

    async def log_audit(
        self, agent_name: str, tool_name: str, params: dict,
        result: dict | None = None, ip_address: str | None = None,
    ) -> None:
        """写入审计日志到 PG audit_log"""
        try:
            import asyncpg
            import json
            settings = get_settings()
            conn = await asyncpg.connect(settings.pg_dsn)
            try:
                await conn.execute(
                    """INSERT INTO audit_log (user_id, action, resource, detail, ip_address)
                       VALUES ($1, $2, $3, $4::jsonb, $5)""",
                    agent_name,
                    "function_call",
                    tool_name,
                    json.dumps({"params": str(params)[:500], "has_result": result is not None}),
                    ip_address,
                )
            finally:
                await conn.close()
        except Exception as e:
            logger.error("fc_audit_log_error", error=str(e))

    async def validate_and_log(
        self, agent_name: str, tool_name: str, params: dict, ip_address: str | None = None,
    ) -> tuple[bool, str]:
        """综合校验：白名单 + 频率限制 + 审计日志"""
        if not self.check_whitelist(tool_name):
            return False, f"Tool '{tool_name}' not in whitelist"

        if not self.check_rate_limit(agent_name):
            return False, f"Rate limit exceeded for agent '{agent_name}'"

        await self.log_audit(agent_name, tool_name, params, ip_address=ip_address)
        return True, "ok"
