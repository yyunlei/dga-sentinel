"""
N-gram 特征提取器 — 复用现有 TF-IDF 向量化器
从 predict.py bin_predict 类的 ngrams_features_per_sample / calc_ngrams_features 重构
"""

from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy.stats import skew, kurtosis


_ARTIFACTS_DIR = Path(__file__).resolve().parent.parent.parent / "artifacts" / "binary"


class NgramFeatureExtractor:
    """N-gram TF-IDF 特征提取（复用已训练的向量化器）"""

    def __init__(self, artifacts_dir: Path | None = None):
        base = artifacts_dir or _ARTIFACTS_DIR
        self.unigrams = joblib.load(base / "unigram_vectorizer.pkl")
        self.bigrams = joblib.load(base / "bigram_vectorizer.pkl")
        self.trigrams = joblib.load(base / "trigram_vectorizer.pkl")
        self.scaler = joblib.load(base / "scaler.pkl")

    # 与 artifacts/binary 中 scaler 训练时的特征名一致（UNI-*/BI-*/TRI-*）
    _NGRAM_COLUMNS = [
        "UNI-MEAN", "UNI-VAR", "UNI-PVAR", "UNI-STD", "UNI-PSTD", "UNI-SKE", "UNI-KUR",
        "BI-MEAN", "BI-VAR", "BI-PVAR", "BI-STD", "BI-PSTD", "BI-SKE", "BI-KUR",
        "TRI-MEAN", "TRI-VAR", "TRI-PVAR", "TRI-STD", "TRI-PSTD", "TRI-SKE", "TRI-KUR",
    ]

    @staticmethod
    def _matrix_stats(matrix, prefix: str) -> dict[str, float]:
        """从 TF-IDF 矩阵提取统计特征（与原 ngrams_features_per_sample 一致）"""
        dense = matrix.toarray()
        row = dense[0]
        m_mean = float(np.mean(row))
        m_std = float(np.std(row))
        return {
            f"{prefix}_mean": m_mean,
            f"{prefix}_var": m_std * m_std if m_std != 0 else 0.0,
            f"{prefix}_min": float(np.min(row)),
            f"{prefix}_std": m_std,
            f"{prefix}_max": float(np.max(row)),
            f"{prefix}_skew": float(skew(row)),
            f"{prefix}_kurtosis": float(kurtosis(row)),
        }

    def extract(self, domain: str) -> dict[str, float]:
        """提取 n-gram 统计特征（21 维），键与 scaler 训练时列名一致"""
        uni_matrix = self.unigrams.transform([domain])
        bi_matrix = self.bigrams.transform([domain])
        tri_matrix = self.trigrams.transform([domain])
        features = {}
        for matrix, short in [(uni_matrix, "UNI"), (bi_matrix, "BI"), (tri_matrix, "TRI")]:
            s = self._matrix_stats(matrix, short.lower())
            features[f"{short}-MEAN"] = s[f"{short.lower()}_mean"]
            features[f"{short}-VAR"] = s[f"{short.lower()}_var"]
            features[f"{short}-PVAR"] = s[f"{short.lower()}_min"]
            features[f"{short}-STD"] = s[f"{short.lower()}_std"]
            features[f"{short}-PSTD"] = s[f"{short.lower()}_max"]
            features[f"{short}-SKE"] = s[f"{short.lower()}_skew"]
            features[f"{short}-KUR"] = s[f"{short.lower()}_kurtosis"]
        return features

    def extract_and_scale(self, domain: str, lexical_features: dict) -> np.ndarray:
        """
        提取完整特征向量并缩放（与 scaler 训练时列顺序一致）
        lexical_features: extract_lexical_features() 的输出
        返回: 缩放后的特征向量 (1, n_features)
        """
        ngram_feats = self.extract(domain)
        feature_columns = [
            "N", "LCc", "LCv", "LCn",
            "L_tld", "Rc_tld", "Rv_tld", "Rn_tld", "Rl_tld", "Rs_tld",
            "L_sld", "Rc_sld", "Rv_sld", "Rn_sld", "Rl_sld", "Rs_sld",
            "L_sub", "Rc_sub", "Rv_sub", "Rn_sub", "Rl_sub", "Rs_sub",
        ]
        row = [lexical_features[c] for c in feature_columns] + [ngram_feats[c] for c in self._NGRAM_COLUMNS]
        X = pd.DataFrame([row], columns=feature_columns + self._NGRAM_COLUMNS)
        return self.scaler.transform(X)
