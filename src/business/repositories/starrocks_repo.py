"""
Gateway — StarRocks Stream Load 写入（薄包装）
实际 Stream Load 逻辑已下沉到 common.starrocks，此处保持原函数名/签名不变，
以兼容 api/score.py 等上层调用方：
    from business.repositories.starrocks_repo import write_events_to_starrocks
"""

from __future__ import annotations

from typing import Any

from common.starrocks import stream_load

# 表名常量，保持原有引用点不变
TABLE_DGA_EVENTS = "dga_events"


async def write_events_to_starrocks(events: list[dict[str, Any]]) -> bool:
    """
    通过 Stream Load HTTP 接口将事件写入 StarRocks dga_analytics.dga_events。
    单条或批量均可；失败时打日志并返回 False，不抛异常。
    """
    return await stream_load(events, TABLE_DGA_EVENTS)
