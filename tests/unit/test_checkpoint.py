"""Checkpoint 管理测试"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock
from dag.checkpoint import CheckpointManager


class TestCheckpointManager:
    def test_save_and_get_offset(self):
        redis = AsyncMock()
        redis.get.return_value = b"42"
        mgr = CheckpointManager(redis_client=redis, key_prefix="test:")
        asyncio.run(mgr.save_offset("topic1", 0, 42))
        redis.set.assert_called_once()
        offset = asyncio.run(mgr.get_offset("topic1", 0))
        assert offset == 42

    def test_get_offset_none(self):
        redis = AsyncMock()
        redis.get.return_value = None
        mgr = CheckpointManager(redis_client=redis, key_prefix="test:")
        offset = asyncio.run(mgr.get_offset("topic1", 0))
        assert offset is None

    def test_idempotency_check(self):
        redis = AsyncMock()
        redis.exists.return_value = True
        mgr = CheckpointManager(redis_client=redis, key_prefix="test:")
        assert asyncio.run(mgr.is_processed("evt-1")) is True

    def test_mark_processed(self):
        redis = AsyncMock()
        mgr = CheckpointManager(redis_client=redis, key_prefix="test:")
        asyncio.run(mgr.mark_processed("evt-1", ttl=3600))
        redis.set.assert_called_once()

    def test_no_redis_graceful(self):
        mgr = CheckpointManager(redis_client=None)
        asyncio.run(mgr.save_offset("t", 0, 1))
        assert asyncio.run(mgr.get_offset("t", 0)) is None
        assert asyncio.run(mgr.is_processed("x")) is False
