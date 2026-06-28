"""
N-gram 特征构建器 — 完整 char n-gram TF-IDF（bigram + trigram + quadgram）。

与 scripts/train_binary_xgb.py 的 build_matrix 一一对应：拼接顺序固定为
  lexical(22) | entropy(4) | bigram TF-IDF | trigram TF-IDF | quadgram TF-IDF
XGBoost 树模型对特征缩放不敏感，**不使用 StandardScaler**，保持稀疏。
"""

from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import scipy.sparse as sp

from common.features.lexical import LEXICAL_COLUMNS
from common.features.entropy import ENTROPY_COLUMNS


_ARTIFACTS_DIR = Path(__file__).resolve().parent.parent.parent / "artifacts" / "binary"


class NgramFeatureExtractor:
    """完整 n-gram TF-IDF 特征构建（复用已训练的向量化器）。"""

    # 训练时保存的向量化器文件名（顺序即拼接顺序）
    _VECTORIZER_FILES = ["bigram_vectorizer.pkl", "trigram_vectorizer.pkl", "quadgram_vectorizer.pkl"]

    def __init__(self, artifacts_dir: Path | None = None):
        base = Path(artifacts_dir) if artifacts_dir else _ARTIFACTS_DIR
        self.vectorizers = [joblib.load(base / f) for f in self._VECTORIZER_FILES]

    def build(self, domain: str, lexical_features: dict, entropy_features: dict) -> "sp.csr_matrix":
        """
        构建完整特征向量（稀疏，1 行）。
        lexical_features: extract_lexical_features() 输出（22 维）
        entropy_features: extract_entropy_features() 输出（4 维）
        返回: (1, 26 + Σ ngram_vocab) 的 CSR 稀疏矩阵
        """
        lex = np.array([[lexical_features[c] for c in LEXICAL_COLUMNS]], dtype=np.float32)
        ent = np.array([[entropy_features[c] for c in ENTROPY_COLUMNS]], dtype=np.float32)
        blocks = [sp.csr_matrix(lex), sp.csr_matrix(ent)] + [v.transform([domain]) for v in self.vectorizers]
        return sp.hstack(blocks).tocsr()
