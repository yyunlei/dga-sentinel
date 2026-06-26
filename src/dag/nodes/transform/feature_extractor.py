"""
特征提取节点 — 调用 ai.scoring 的特征提取器
"""

from __future__ import annotations

from typing import Any

from dag.nodes.base import BaseNode
from ai.scoring.features.lexical import extract_lexical_features
from ai.scoring.features.entropy import extract_entropy_features


class FeatureExtractorNode(BaseNode):
    """提取域名特征（词法 + 熵 + 可选 n-gram）"""

    node_type = "feature_extractor"

    async def process(self, state: dict[str, Any]) -> dict[str, Any]:
        domain = state.get("domain", "")
        if not domain:
            state["features"] = {}
            return state

        extractors = self.config.get("extractors", ["lexical", "entropy"])
        features = {}

        if "lexical" in extractors:
            features.update(extract_lexical_features(domain))

        if "entropy" in extractors:
            features.update(extract_entropy_features(domain))

        state["features"] = features
        return state
