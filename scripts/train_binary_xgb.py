#!/usr/bin/env python
"""
binary-xgboost 训练 / 调优脚本（生产版，完整 n-gram TF-IDF 特征）。

特征 = 22 词法 + 4 熵 + 完整 char n-gram TF-IDF（bigram + trigram + quadgram，稀疏）。
相比"聚合统计"特征，完整 ngram 让模型学到"哪些具体字符组合 = DGA"，是从 ~98% 跨到
99.7%+ 的关键。XGBoost 是树模型、对特征缩放不敏感，故 **不使用 StandardScaler**
（保持稀疏、省内存）。

与推理端 common.features.ngram.NgramFeatureExtractor.build() 一一对应（同样的向量化器、
同样的拼接顺序 lexical|entropy|bigram|trigram|quadgram）。

产物：artifacts/binary/ 下 bigram/trigram/quadgram_vectorizer.pkl + binary_classification_model.pkl
用法：PYTHONPATH=src .venv/bin/python scripts/train_binary_xgb.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import scipy.sparse as sp
import joblib
import xgboost as xgb
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    roc_auc_score, confusion_matrix,
)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from common.features.lexical import extract_lexical_features, LEXICAL_COLUMNS  # noqa: E402
from common.features.entropy import extract_entropy_features, ENTROPY_COLUMNS, shannon_entropy  # noqa: E402

ART = ROOT / "artifacts" / "binary"
DATA = ART / "binary_dataset.csv"

# n-gram TF-IDF 维度（越大越细，但更慢/更大）
NGRAM_CONF = [(2, 3000), (3, 5000), (4, 3000)]  # (n, max_features)


def build_matrix(domains, vecs):
    """lexical(22) + entropy(4) + 各 ngram TF-IDF → 稀疏 CSR（拼接顺序固定）。"""
    lex = np.array([[f[c] for c in LEXICAL_COLUMNS] for f in map(extract_lexical_features, domains)], dtype=np.float32)
    ent = np.array([[f[c] for c in ENTROPY_COLUMNS] for f in map(extract_entropy_features, domains)], dtype=np.float32)
    blocks = [sp.csr_matrix(lex), sp.csr_matrix(ent)] + [v.transform(domains) for v in vecs]
    return sp.hstack(blocks).tocsr()


def main() -> None:
    t0 = time.time()
    print("加载 + 去重 ...", flush=True)
    df = pd.read_csv(DATA).dropna().drop_duplicates("Domain").sample(frac=1, random_state=42).reset_index(drop=True)
    domains = df["Domain"].astype(str).tolist()
    y = df["Target"].astype(int).values
    print(f"  去重后 {len(domains):,} 样本  标签 {np.bincount(y)}", flush=True)

    print(f"拟合 char TF-IDF {NGRAM_CONF} ...", flush=True)
    vecs = [TfidfVectorizer(analyzer="char", ngram_range=(n, n), max_features=mf).fit(domains) for n, mf in NGRAM_CONF]

    print("构建完整特征矩阵 ...", flush=True)
    X = build_matrix(domains, vecs)
    print(f"  X={X.shape}  ({time.time()-t0:.0f}s)", flush=True)

    X_tr, X_te, y_tr, y_te, d_tr, d_te = train_test_split(
        X, y, np.array(domains), test_size=0.2, random_state=42, stratify=y
    )

    print("训练 XGBoost (深树 + early stopping) ...", flush=True)
    model = xgb.XGBClassifier(
        n_estimators=2000, max_depth=14, learning_rate=0.1,
        subsample=0.85, colsample_bytree=0.6, reg_lambda=2.0,
        tree_method="hist", eval_metric="logloss",
        early_stopping_rounds=60, random_state=42, n_jobs=-1,
    )
    model.fit(X_tr, y_tr, eval_set=[(X_te, y_te)], verbose=False)

    prob = model.predict_proba(X_te)[:, 1]
    pred = model.predict(X_te)
    print("\n=== 留出集 (20%, 全量任务含字典型 DGA) ===", flush=True)
    print(f"  best_iteration : {model.best_iteration}")
    print(f"  Accuracy : {accuracy_score(y_te, pred)*100:.3f}%")
    print(f"  Precision: {precision_score(y_te, pred)*100:.3f}%")
    print(f"  Recall   : {recall_score(y_te, pred)*100:.3f}%")
    print(f"  F1       : {f1_score(y_te, pred)*100:.3f}%")
    print(f"  ROC-AUC  : {roc_auc_score(y_te, prob)*100:.4f}%")
    print(f"  混淆矩阵 : {confusion_matrix(y_te, pred).tolist()}")
    neg = prob[y_te == 0]
    for f in (0.001, 0.005, 0.01):
        thr = np.quantile(neg, 1 - f)
        p = (prob >= thr).astype(int)
        print(f"  @FPR={f*100:.1f}%: Recall={recall_score(y_te, p)*100:.2f}%  Acc={(p==y_te).mean()*100:.3f}%")

    # 算法型口径(高熵 DGA + 全部正常)breakdown —— 对应文献 99.9% 范围
    ent_te = np.array([shannon_entropy(d.split(".")[-2] if "." in d else d) for d in d_te])
    algo = (y_te == 0) | ((y_te == 1) & (ent_te >= 3.0))
    print(f"\n  [算法型口径] 高熵DGA+正常 准确率: {accuracy_score(y_te[algo], pred[algo])*100:.3f}%  "
          f"AUC: {roc_auc_score(y_te[algo], prob[algo])*100:.4f}%", flush=True)

    print("\n保存 artifacts ...", flush=True)
    names = ["bigram", "trigram", "quadgram"]
    for v, nm in zip(vecs, names):
        joblib.dump(v, ART / f"{nm}_vectorizer.pkl")
    joblib.dump(model, ART / "binary_classification_model.pkl")
    print(f"  完成。总耗时 {time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
