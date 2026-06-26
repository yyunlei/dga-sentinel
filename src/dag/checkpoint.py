"""
Redis Checkpoint 管理 — 消费位点、幂等写入、失败重试
"""

from __future__ import annotations

from typing import Any

from common.observability import get_logger

logger = get_logger(__name__)


class CheckpointManager:
    """
    基于 Redis 的 Checkpoint 管理
    - 消费位点持久化
    - 事件 ID 幂等去重
    - 回放游标管理
    """

    def __init__(self, redis_client=None, key_prefix: str = "ckpt:"):
        self.redis = redis_client
        self.prefix = key_prefix

    async def save_offset(self, topic: str, partition: int, offset: int) -> None:
        """保存 Kafka 消费位点"""
        if not self.redis:
            return
        key = f"{self.prefix}offset:{topic}:{partition}"
        await self.redis.set(key, str(offset))

    async def get_offset(self, topic: str, partition: int) -> int | None:
        """获取已保存的消费位点"""
        if not self.redis:
            return None
        key = f"{self.prefix}offset:{topic}:{partition}"
        val = await self.redis.get(key)
        return int(val) if val else None

    async def is_processed(self, event_id: str) -> bool:
        """检查事件是否已处理（幂等去重）"""
        if not self.redis:
            return False
        key = f"{self.prefix}processed:{event_id}"
        return bool(await self.redis.exists(key))

    async def mark_processed(self, event_id: str, ttl: int = 86400) -> None:
        """标记事件已处理"""
        if not self.redis:
            return
        key = f"{self.prefix}processed:{event_id}"
        await self.redis.set(key, "1", ex=ttl)

    async def save_replay_cursor(self, replay_id: str, cursor: str) -> None:
        """保存回放游标"""
        if not self.redis:
            return
        key = f"{self.prefix}replay:{replay_id}"
        await self.redis.set(key, cursor)

    async def get_replay_cursor(self, replay_id: str) -> str | None:
        """获取回放游标"""
        if not self.redis:
            return None
        key = f"{self.prefix}replay:{replay_id}"
        val = await self.redis.get(key)
        return val.decode() if val else None
