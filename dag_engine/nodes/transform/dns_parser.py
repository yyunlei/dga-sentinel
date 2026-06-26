"""
DNS 日志解析节点
"""

from __future__ import annotations

from typing import Any

from dag_engine.nodes.base import BaseNode


class DNSParserNode(BaseNode):
    """解析 DNS 查询日志，提取域名和元数据"""

    node_type = "dns_parser"

    async def process(self, state: dict[str, Any]) -> dict[str, Any]:
        raw = state.get("raw_data", {})
        fields = self.config.get("fields", ["query_name", "query_type", "src_ip", "timestamp"])

        # 支持多种输入格式
        if isinstance(raw, dict):
            parsed = {f: raw.get(f, "") for f in fields}
        elif isinstance(raw, str):
            # 简单格式: "domain query_type src_ip timestamp"
            parts = raw.strip().split()
            parsed = {}
            for i, f in enumerate(fields):
                parsed[f] = parts[i] if i < len(parts) else ""
        else:
            parsed = {"query_name": str(raw)}

        state["domain"] = parsed.get("query_name", "")
        state["src_ip"] = parsed.get("src_ip", "")
        state["query_type"] = parsed.get("query_type", "A")
        state["event_timestamp"] = parsed.get("timestamp", "")
        state["parsed"] = parsed
        return state
