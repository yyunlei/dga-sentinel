"""
阈值分层节点 — 按租户/业务动态阈值
"""

from __future__ import annotations

from typing import Any

from dag_engine.nodes.base import BaseNode
from shared.constants import DEFAULT_DGA_THRESHOLD


class ThresholdNode(BaseNode):
    """动态阈值过滤：根据租户配置调整判定阈值"""

    node_type = "threshold"

    async def process(self, state: dict[str, Any]) -> dict[str, Any]:
        score = state.get("score", 0.0)
        tenant_id = state.get("tenant_id", "default")

        # 从配置获取租户阈值
        tenants = self.config.get("tenants", {})
        threshold = tenants.get(tenant_id, self.config.get("default", DEFAULT_DGA_THRESHOLD))

        state["threshold"] = threshold
        state["is_dga"] = score >= threshold

        # 分层严重度
        if score >= 0.95:
            state["severity"] = "CRITICAL"
        elif score >= 0.85:
            state["severity"] = "HIGH"
        elif score >= threshold:
            state["severity"] = "MEDIUM"
        else:
            state["severity"] = "LOW"

        state["rules_applied"] = state.get("rules_applied", []) + [f"threshold:{threshold}"]
        return state
