"""
Redis-backed 滑动窗口限流中间件
开发模式下回退到内存限流
"""

from __future__ import annotations

import time
from collections import defaultdict

from fastapi import HTTPException, Request

from common.observability import RATE_LIMIT_REJECTED


class InMemoryRateLimiter:
    """内存限流器（开发/测试用）"""

    def __init__(self, max_requests: int = 600, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window = window_seconds
        self._buckets: dict[str, list[float]] = defaultdict(list)

    async def check(self, key: str, limit: int | None = None) -> bool:
        max_req = limit or self.max_requests
        now = time.time()
        bucket = self._buckets[key]
        self._buckets[key] = [t for t in bucket if now - t < self.window]
        if len(self._buckets[key]) >= max_req:
            return False
        self._buckets[key].append(now)
        return True


class RedisRateLimiter:
    """Redis 滑动窗口限流器"""

    def __init__(self, redis_url: str, max_requests: int = 600, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window = window_seconds
        self._redis = None
        self._redis_url = redis_url

    async def _get_redis(self):
        if self._redis is None:
            try:
                import redis.asyncio as aioredis
                self._redis = aioredis.from_url(self._redis_url, decode_responses=True)
            except Exception:
                return None
        return self._redis

    async def check(self, key: str, limit: int | None = None) -> bool:
        max_req = limit or self.max_requests
        r = await self._get_redis()
        if r is None:
            return True  # Redis 不可用时放行

        redis_key = f"ratelimit:{key}"
        now = time.time()
        pipe = r.pipeline()
        pipe.zremrangebyscore(redis_key, 0, now - self.window)
        pipe.zadd(redis_key, {str(now): now})
        pipe.zcard(redis_key)
        pipe.expire(redis_key, self.window + 1)
        results = await pipe.execute()
        count = results[2]
        return count <= max_req


_limiter: InMemoryRateLimiter | RedisRateLimiter | None = None


def get_limiter() -> InMemoryRateLimiter | RedisRateLimiter:
    global _limiter
    if _limiter is None:
        from common.config import get_settings
        settings = get_settings()
        if settings.is_dev:
            _limiter = InMemoryRateLimiter(settings.rate_limit_per_minute)
        else:
            _limiter = RedisRateLimiter(settings.redis_url, settings.rate_limit_per_minute)
    return _limiter


async def rate_limit_check(request: Request) -> None:
    """限流检查（按 IP 或 tenant_id）"""
    key = request.headers.get("X-Tenant-ID", request.client.host if request.client else "unknown")
    limiter = get_limiter()
    if not await limiter.check(key):
        RATE_LIMIT_REJECTED.labels(tenant_id=key).inc()
        raise HTTPException(429, "Rate limit exceeded")