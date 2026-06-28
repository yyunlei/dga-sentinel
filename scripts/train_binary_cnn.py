#!/usr/bin/env python
"""
binary DGA 检测 — 字符级 1D-CNN（在 Docker scoring 容器内训练，容器有 TF）。

读原始域名字符序列 → Embedding → 多尺度 Conv1D → GlobalMaxPool → Dense → sigmoid。
比 XGBoost-on-统计特征 能捕捉位置/序列模式（可发音 DGA）。

用法（容器内）:  python /app/train_binary_cnn.py [sample_n] [epochs]
产物:  /app/artifacts/binary/binary_cnn.keras + char_vocab.json
"""
import json
import sys
import time

import numpy as np
import pandas as pd
import tensorflow as tf
from sklearn.model_selection import train_test_split

DATA = "/app/artifacts/binary/binary_dataset.csv"
MAXLEN = 64
SAMPLE = int(sys.argv[1]) if len(sys.argv) > 1 else 0   # 0 = 全量
EPOCHS = int(sys.argv[2]) if len(sys.argv) > 2 else 8


def main():
    t0 = time.time()
    df = pd.read_csv(DATA).dropna()
    if SAMPLE:
        df = df.sample(n=SAMPLE, random_state=42)
    df = df.sample(frac=1, random_state=42).reset_index(drop=True)
    domains = df["Domain"].astype(str).str.lower().tolist()
    y = df["Target"].astype(int).values
    print(f"样本 {len(domains):,}  标签 {np.bincount(y)}", flush=True)

    # 字符词表
    chars = sorted({c for d in domains for c in d})
    vocab = {c: i + 1 for i, c in enumerate(chars)}  # 0 = pad
    print(f"字符表大小 {len(vocab)}", flush=True)

    def encode(dl):
        arr = np.zeros((len(dl), MAXLEN), dtype=np.int32)
        for i, d in enumerate(dl):
            for j, c in enumerate(d[:MAXLEN]):
                arr[i, j] = vocab.get(c, 0)
        return arr

    X = encode(domains)
    X_tmp, X_te, y_tmp, y_te = train_test_split(X, y, test_size=0.15, random_state=7, stratify=y)
    X_tr, X_val, y_tr, y_val = train_test_split(X_tmp, y_tmp, test_size=0.15, random_state=7, stratify=y_tmp)
    print(f"train={len(y_tr):,} val={len(y_val):,} test={len(y_te):,}  ({time.time()-t0:.0f}s)", flush=True)

    inp = tf.keras.Input(shape=(MAXLEN,), dtype="int32")
    emb = tf.keras.layers.Embedding(len(vocab) + 1, 64, mask_zero=False)(inp)
    convs = []
    for k in (2, 3, 4, 5):
        c = tf.keras.layers.Conv1D(128, k, activation="relu", padding="same")(emb)
        c = tf.keras.layers.GlobalMaxPooling1D()(c)
        convs.append(c)
    x = tf.keras.layers.Concatenate()(convs)
    x = tf.keras.layers.Dropout(0.3)(x)
    x = tf.keras.layers.Dense(128, activation="relu")(x)
    x = tf.keras.layers.Dropout(0.3)(x)
    out = tf.keras.layers.Dense(1, activation="sigmoid")(x)
    model = tf.keras.Model(inp, out)
    model.compile(optimizer=tf.keras.optimizers.Adam(1e-3), loss="binary_crossentropy", metrics=["accuracy"])

    es = tf.keras.callbacks.EarlyStopping(monitor="val_accuracy", patience=2, restore_best_weights=True)
    model.fit(X_tr, y_tr, validation_data=(X_val, y_val), epochs=EPOCHS, batch_size=512, callbacks=[es], verbose=2)

    prob = model.predict(X_te, batch_size=1024, verbose=0).ravel()
    pred = (prob >= 0.5).astype(int)
    acc = (pred == y_te).mean()
    from sklearn.metrics import roc_auc_score, precision_score, recall_score
    print("\n=== 留出集 (test, 0.5 阈值) ===", flush=True)
    print(f"  Accuracy : {acc:.5f}")
    print(f"  Precision: {precision_score(y_te, pred):.5f}")
    print(f"  Recall   : {recall_score(y_te, pred):.5f}")
    print(f"  ROC-AUC  : {roc_auc_score(y_te, prob):.5f}")
    neg = prob[y_te == 0]
    print("  阈值@FPR  Recall  Accuracy", flush=True)
    for f in (0.001, 0.005, 0.01):
        thr = np.quantile(neg, 1 - f)
        p = (prob >= thr).astype(int)
        print(f"   FPR={f*100:.1f}%  R={recall_score(y_te,p)*100:.2f}%  acc={(p==y_te).mean()*100:.2f}%", flush=True)

    model.save("/app/artifacts/binary/binary_cnn.keras")
    json.dump(vocab, open("/app/artifacts/binary/char_vocab.json", "w"))
    print(f"\n保存完成。总耗时 {time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
