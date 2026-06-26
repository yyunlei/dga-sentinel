"""
多模型融合 — 加权 ensemble
组合二分类 + 多分类模型的输出
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from scoring_service.models.binary_model import BinaryModel
from scoring_service.models.multi_model import MultiClassModel


@dataclass
class ScoringResult:
    domain: str
    score: float           # 风险分数 [0, 1]
    is_dga: bool
    family: str | None
    family_confidence: float | None
    model_version: str
    features: dict | None = None


class EnsembleScorer:
    """
    两阶段评分 + 可选加权融合：
    1. XGBoost 二分类 → 是否 DGA + 概率
    2. 如果是 DGA → CNN-Attention 多分类 → 家族识别
    3. 加权模式：final_score = binary_score * w1 + multi_confidence * w2
    """

    def __init__(
        self,
        binary_model: BinaryModel,
        multi_model: MultiClassModel,
        threshold: float = 0.5,
        weights: dict[str, float] | None = None,
    ):
        self.binary = binary_model
        self.multi = multi_model
        self.threshold = threshold
        self.weights = weights  # {"binary_weight": 0.6, "multi_weight": 0.4}

    def score(self, domain: str) -> ScoringResult:
        """单域名评分"""
        label, proba = self.binary.predict(domain)

        family = None
        family_confidence = None

        if label == 1 and proba >= self.threshold:
            top_families = self.multi.predict(domain, top_k=1)
            if top_families:
                family = top_families[0]["family"]
                family_confidence = top_families[0]["confidence"]

        # 加权融合
        final_score = proba
        if self.weights and family_confidence is not None:
            w1 = self.weights.get("binary_weight", 0.6)
            w2 = self.weights.get("multi_weight", 0.4)
            final_score = min(1.0, proba * w1 + family_confidence * w2)

        return ScoringResult(
            domain=domain,
            score=final_score,
            is_dga=(label == 1),
            family=family,
            family_confidence=family_confidence,
            model_version=f"{self.binary.version}+{self.multi.version}",
        )

    def score_batch(self, domains: list[str]) -> list[ScoringResult]:
        """批量评分（串行）"""
        return [self.score(d) for d in domains]

    def score_batch_parallel(self, domains: list[str], max_workers: int = 4) -> list[ScoringResult]:
        """批量评分（并行）"""
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            return list(pool.map(self.score, domains))
