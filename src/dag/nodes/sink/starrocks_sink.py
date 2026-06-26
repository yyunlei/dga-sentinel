"""
StarRocks 输出节点 — 通过 Stream Load HTTP 写入 OLAP 分析表
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from common.starrocks import stream_load
from dag.nodes.base import BaseNode, logger


class StarRocksSinkNode(BaseNode):
    """将事件写入 StarRocks 分析表（dga_analytics.dga_events）"""

    node_type = "starrocks_sink"

    async def process(self, state: dict[str, Any]) -> dict[str, Any]:
        condition = self.config.get("condition", "always")
        if condition != "always" and not state.get("is_dga", False):
            return state

        table = self.config.get("table", "dga_events")

        # StarRocks DATETIME 需要 "%Y-%m-%d %H:%M:%S" 格式（与 detection_service 一致）
        event_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        row = {
            "event_id": state.get("event_id", ""),
            "trace_id": state.get("trace_id", ""),
            "event_time": event_time,
            "domain": state.get("domain", ""),
            "src_ip": state.get("src_ip", ""),
            "score": float(state.get("score", 0.0)),
            "is_dga": bool(state.get("is_dga", False)),
            "family": state.get("family") or "",
            "family_confidence": float(state.get("family_confidence") or 0.0),
            "model_version": state.get("model_version", ""),
            "pipeline_id": self.pipeline_id,
            "tenant_id": state.get("tenant_id", "default"),
            "severity": state.get("severity", "LOW"),
        }

        ok = await stream_load([row], table)
        if ok:
            logger.info(
                "starrocks_sink_written",
                table=table,
                domain=state.get("domain"),
                pipeline_id=self.pipeline_id,
            )
        else:
            logger.warning(
                "starrocks_sink_write_failed",
                table=table,
                domain=state.get("domain"),
                pipeline_id=self.pipeline_id,
            )

        state.setdefault("sinks_written", []).append(f"starrocks:{table}")
        return state
