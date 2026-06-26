"""
二分类模型封装 — 复用现有 XGBoost 模型
从 predict.py bin_predict 类重构为无状态服务
"""

from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np

from common.features.lexical import extract_lexical_features
from common.features.ngram import NgramFeatureExtractor


class BinaryModel:
    """XGBoost 二分类模型：Benign(0) vs Malware(1)"""

    def __init__(self, model_path: str, artifacts_dir: str | None = None):
        self.model = joblib.load(model_path)
        base = Path(artifacts_dir) if artifacts_dir else Path(model_path).parent
        self.ngram_extractor = NgramFeatureExtractor(base)
        self.version = "v1.0.0"

    def predict(self, domain: str) -> tuple[int, float]:
        """
        预测域名是否为 DGA
        返回: (label, probability)
            label: 0=benign, 1=malware
            probability: malware 概率 [0, 1]
        """
        lexical = extract_lexical_features(domain)
        X = self.ngram_extractor.extract_and_scale(domain, lexical)

        label = int(self.model.predict(X)[0])

        # 获取概率（如果模型支持）
        if hasattr(self.model, "predict_proba"):
            proba = float(self.model.predict_proba(X)[0][1])
        else:
            proba = float(label)

        return label, proba

    def predict_batch(self, domains: list[str]) -> list[tuple[int, float]]:
        """批量预测"""
        return [self.predict(d) for d in domains]
