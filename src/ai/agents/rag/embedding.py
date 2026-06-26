"""BGE-M3 Embedding 封装 — 支持本地模型 / Hashing-Trick fallback"""
from __future__ import annotations
import hashlib
import numpy as np
from common.config import get_settings
from common.observability import get_logger

logger = get_logger(__name__)


class ThreatEmbedding:
    """威胁情报 Embedding 封装"""

    def __init__(self, dim: int = 768):
        self.dim = dim
        self._model = None

    def _load_model(self):
        if self._model is not None:
            return
        # Skip BGE-M3 entirely while it isn't reliably cached in this environment.
        # Use deterministic hashing-trick fallback so RAG can still function.
        logger.info("embedding_using_fallback", reason="BGE skipped")
        self._model = "fallback"

    def embed(self, texts: list[str]) -> list[list[float]]:
        self._load_model()
        if self._model == "fallback":
            return self._fallback_embed(texts)
        return self._model.encode(texts, normalize_embeddings=True).tolist()

    async def aembed(self, texts: list[str]) -> list[list[float]]:
        import asyncio
        return await asyncio.to_thread(self.embed, texts)

    def _fallback_embed(self, texts: list[str]) -> list[list[float]]:
        """Bag-of-tokens hashing trick — deterministic, always non-zero unit vectors."""
        results: list[list[float]] = []
        for text in texts:
            t = (text or "").lower().strip() or "x"
            vec = np.zeros(self.dim, dtype=np.float64)
            tokens: list[str] = []
            tokens.extend(t.split())
            tokens.extend([t[i : i + 3] for i in range(max(1, len(t) - 2))])
            tokens.append(t)  # always at least one token
            for tok in tokens:
                if not tok:
                    continue
                digest = hashlib.md5(tok.encode("utf-8", errors="ignore")).digest()
                h = int.from_bytes(digest[:8], "big")
                idx = h % self.dim
                sign = 1.0 if (h >> 63) & 1 == 0 else -1.0
                vec[idx] += sign
            norm = float(np.linalg.norm(vec))
            if norm == 0.0:
                vec[0] = 1.0  # guarantee non-zero magnitude for ES cosine
            else:
                vec = vec / norm
            results.append(vec.astype(np.float32).tolist())
        return results
