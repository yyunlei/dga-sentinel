"""
多分类模型封装 — 复用现有 CNN-Attention 模型
从 predict.py multi_predict 类重构为无状态服务
"""

from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
from tensorflow.keras.models import load_model
from tensorflow.keras.preprocessing.sequence import pad_sequences


class MultiClassModel:
    """CNN-Attention 多分类模型：识别恶意软件家族"""

    def __init__(self, model_path: str, artifacts_dir: str | None = None):
        base = Path(artifacts_dir) if artifacts_dir else Path(model_path).parent
        self.model = load_model(model_path)
        self.tokenizer = joblib.load(base / "tokenizer.pkl")
        self.encoder = joblib.load(base / "encoder_multi.pkl")
        self.max_sequence_length = 50
        self.version = "v1.0.0"

    def predict(self, domain: str, top_k: int = 3) -> list[dict]:
        """
        预测恶意软件家族
        返回: [{"family": str, "confidence": float}, ...]
        """
        sequence = self.tokenizer.texts_to_sequences([domain])
        padded = pad_sequences(sequence, maxlen=self.max_sequence_length, padding="post")

        prediction = self.model.predict(padded, verbose=0)
        top_indices = np.argsort(prediction[0])[-top_k:][::-1]
        top_probs = prediction[0][top_indices]
        top_classes = self.encoder.inverse_transform(top_indices)

        return [
            {"family": str(top_classes[i]), "confidence": float(top_probs[i])}
            for i in range(top_k)
        ]

    def predict_batch(self, domains: list[str], top_k: int = 3) -> list[list[dict]]:
        """批量预测"""
        sequences = self.tokenizer.texts_to_sequences(domains)
        padded = pad_sequences(sequences, maxlen=self.max_sequence_length, padding="post")

        predictions = self.model.predict(padded, verbose=0)
        results = []
        for pred in predictions:
            top_indices = np.argsort(pred)[-top_k:][::-1]
            top_probs = pred[top_indices]
            top_classes = self.encoder.inverse_transform(top_indices)
            results.append([
                {"family": str(top_classes[i]), "confidence": float(top_probs[i])}
                for i in range(top_k)
            ])
        return results
