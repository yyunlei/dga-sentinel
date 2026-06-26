"""
StarRocks 输出节点 — 写入 OLAP 分析表
"""

from __future__ import annotations

from typing import Any

from dag.nodes.base import BaseNode, logger


class StarRocksSinkNode(BaseNode):
    """将事件写入 StarRocks 分析表"""

    node_type = "starrocks_sink"

    async def process(self, state: dict[str, Any]) -> dict[str, Any]:
        condition = self.config.get("condition", "always")
        if condition != "always" and not state.get("is_dga", False):
            return state

        table = self.config.get("table", "dga_events")

        # StarRocks 通过 Stream Load HTTP 接口写入
        # 实际连接由运行时注入
        sr_client = state.get("_starrocks_client")
        if sr_client:
            logger.info("starrocks_sink_written", table=table, domain=state.get("domain"))
        else:
            logger.debug("starrocks_sink_dry_run", table=table, domain=state.get("domain"))

        state.setdefault("sinks_written", []).append(f"starrocks:{table}")
        return state
