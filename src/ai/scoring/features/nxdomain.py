"""
NXDOMAIN 比例特征 — 基于滑动窗口统计
需要 Redis 存储窗口内的 NXDOMAIN 计数
"""

from __future__ import annotations

from datetime import datetime, timezone


class NXDomainTracker:
    """跟踪源 IP 的 NXDOMAIN 比例（窗口统计）"""

    def __init__(self, redis_client=None, window_seconds: int = 60):
        self.redis = redis_client
        self.window = window_seconds

    async def record_query(self, src_ip: str, is_nxdomain: bool) -> None:
        """记录一次 DNS 查询"""
        if not self.redis:
            return
        now = int(datetime.now(timezone.utc).timestamp())
        key_total = f"nxdomain:total:{src_ip}"
        key_nx = f"nxdomain:nx:{src_ip}"

        pipe = self.redis.pipeline()
        pipe.incr(key_total)
        pipe.expire(key_total, self.window * 2)
        if is_nxdomain:
            pipe.incr(key_nx)
            pipe.expire(key_nx, self.window * 2)
        await pipe.execute()

    async def get_nxdomain_ratio(self, src_ip: str) -> float:
        """获取源 IP 的 NXDOMAIN 比例"""
        if not self.redis:
            return 0.0
        total = await self.redis.get(f"nxdomain:total:{src_ip}")
        nx = await self.redis.get(f"nxdomain:nx:{src_ip}")
        total = int(total) if total else 0
        nx = int(nx) if nx else 0
        return nx / max(total, 1)

    def extract_features(self, nxdomain_ratio: float) -> dict[str, float]:
        """返回 NXDOMAIN 特征"""
        return {"nxdomain_ratio": nxdomain_ratio}
