"""
文件读取节点 — 从文件/目录读取历史数据（batch 模式）
"""

from __future__ import annotations

from typing import Any

from dag.nodes.base import BaseNode


class FileReaderNode(BaseNode):
    """从文件读取数据（batch 模式使用）"""

    node_type = "file_reader"

    async def process(self, state: dict[str, Any]) -> dict[str, Any]:
        # batch 运行时已将数据行放入 state["raw_message"]
        raw = state.get("raw_message", {})
        state["raw_data"] = raw
        state["source"] = "file"
        state["file_path"] = self.config.get("path", "")
        return state
