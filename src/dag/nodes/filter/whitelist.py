"""
白名单过滤节点 — 静态配置 + Redis 动态名单（反馈闭环驱动）
"""

from __future__ import annotations

from typing import Any

from dag.nodes.base import BaseNode, logger


class WhitelistNode(BaseNode):
    """白名单过滤：匹配白名单的域名直接标记为安全。

    匹配来源（任意一个命中即视为白名单）：
    1. 静态配置（pipeline YAML 的 ``static`` 数组，进程内常驻）
    2. Redis SET ``whitelist:auto`` — 反馈聚合器自动推举
    3. Redis SET ``whitelist:static`` — 管理员手动维护
    """

    node_type = "whitelist"

    REDIS_KEYS = ("whitelist:auto", "whitelist:static")

    def __init__(self, node_id: str, config: dict, pipeline_id: str = ""):
        super().__init__(node_id, config, pipeline_id)
        self._whitelist: set[str] = set()
        self._whitelist.update(config.get("static", []))
        self._redis = None
        self._redis_failed = False

    async def _get_redis(self):
        """懒加载 Redis 客户端；失败后永久跳过，避免每次告警都报错。"""
        if self._redis_failed:
            return None
        if self._redis is None:
            try:
                import redis.asyncio as aioredis
                from common.config import get_settings
                self._redis = aioredis.from_url(
                    get_settings().redis_url, decode_responses=True,
                )
                await self._redis.ping()
            except Exception as e:
                logger.warning("whitelist_redis_unavailable", error=str(e))
                self._redis_failed = True
                self._redis = None
        return self._redis

    async def _hits_dynamic(self, domain: str, sld_tld: str) -> bool:
        r = await self._get_redis()
        if r is None:
            return False
        try:
            for key in self.REDIS_KEYS:
                if await r.sismember(key, domain) or await r.sismember(key, sld_tld):
                    return True
        except Exception as e:
            logger.warning("whitelist_redis_query_failed", error=str(e))
        return False

    async def process(self, state: dict[str, Any]) -> dict[str, Any]:
        domain = state.get("domain", "")
        parts = domain.split(".")
        sld_tld = ".".join(parts[-2:]) if len(parts) >= 2 else domain

        # 1. 静态命中（O(1) 内存查询）
        static_hit = domain in self._whitelist or sld_tld in self._whitelist
        # 2. 动态命中（O(1) Redis SISMEMBER × 4，仅静态未命中时检查）
        dynamic_hit = static_hit or await self._hits_dynamic(domain, sld_tld)

        if static_hit or dynamic_hit:
            state["is_dga"] = False
            state["score"] = 0.0
            source = "static" if static_hit else "dynamic"
            state["rules_applied"] = state.get("rules_applied", []) + [f"whitelist:{source}"]
            logger.debug("whitelist_hit", domain=domain, source=source)

        return state
