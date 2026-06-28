"""评分服务单元测试"""

import pytest
from common.features.lexical import extract_lexical_features, count_char_features
from common.features.entropy import shannon_entropy, extract_entropy_features


class TestLexicalFeatures:
    def test_count_char_features_normal(self):
        L, Rc, Rv, Rn, Rl, Rs = count_char_features("google")
        assert L == 6
        assert Rv > 0  # 有元音
        assert Rc > 0  # 有辅音
        assert Rn == 0  # 无数字

    def test_count_char_features_empty(self):
        L, Rc, Rv, Rn, Rl, Rs = count_char_features("")
        assert L == 0

    def test_extract_lexical_features(self):
        feats = extract_lexical_features("evil.example.com")
        assert feats["N"] == 3  # 有子域名
        assert feats["L_tld"] == 3  # "com"
        assert feats["L_sld"] == 7  # "example"
        assert len(feats) == 22

    def test_extract_lexical_features_no_subdomain(self):
        feats = extract_lexical_features("google.com")
        assert feats["N"] == 2
        assert feats["L_sub"] == 0


class TestEntropyFeatures:
    def test_shannon_entropy_uniform(self):
        # 均匀分布的字符串熵较高
        entropy = shannon_entropy("abcdefgh")
        assert entropy > 2.5

    def test_shannon_entropy_repeated(self):
        # 重复字符的熵为 0
        entropy = shannon_entropy("aaaa")
        assert entropy == 0.0

    def test_shannon_entropy_empty(self):
        assert shannon_entropy("") == 0.0

    def test_extract_entropy_features(self):
        feats = extract_entropy_features("random123.com")
        assert "entropy_full" in feats
        assert "entropy_sld" in feats
        assert "unique_char_ratio" in feats
        assert feats["entropy_full"] > 0


from unittest.mock import patch, MagicMock
import numpy as np


class TestNgramFeatures:
    def test_build_concatenates_lexical_entropy_ngram(self):
        """build() 拼接 lexical(22) + entropy(4) + 各 ngram TF-IDF，返回稀疏 (1, N)。"""
        sparse = pytest.importorskip("scipy.sparse")
        from common.features.ngram import NgramFeatureExtractor
        from common.features.lexical import extract_lexical_features, LEXICAL_COLUMNS
        from common.features.entropy import extract_entropy_features, ENTROPY_COLUMNS

        # 两个 mock 向量化器，各输出 5 / 7 维稀疏
        v1, v2 = MagicMock(), MagicMock()
        v1.transform.return_value = sparse.csr_matrix(np.ones((1, 5), dtype=np.float32))
        v2.transform.return_value = sparse.csr_matrix(np.ones((1, 7), dtype=np.float32))

        ex = NgramFeatureExtractor.__new__(NgramFeatureExtractor)
        ex.vectorizers = [v1, v2]
        lex = extract_lexical_features("evil.example.com")
        ent = extract_entropy_features("evil.example.com")
        X = ex.build("evil.example.com", lex, ent)

        assert sparse.issparse(X)
        # 维度 = 22 词法 + 4 熵 + 5 + 7 = 38
        assert X.shape == (1, len(LEXICAL_COLUMNS) + len(ENTROPY_COLUMNS) + 5 + 7)
        # 前 22 列是词法值（按 LEXICAL_COLUMNS 顺序）
        assert X.toarray()[0, 0] == lex["N"]


import asyncio
from unittest.mock import AsyncMock


class TestNXDomainFeatures:
    def test_extract_features(self):
        from common.features.nxdomain import NXDomainTracker
        tracker = NXDomainTracker(redis_client=None)
        result = tracker.extract_features(0.5)
        assert result == {"nxdomain_ratio": 0.5}

    def test_extract_features_zero(self):
        from common.features.nxdomain import NXDomainTracker
        tracker = NXDomainTracker(redis_client=None)
        assert tracker.extract_features(0.0) == {"nxdomain_ratio": 0.0}

    def test_get_ratio_with_data(self):
        from common.features.nxdomain import NXDomainTracker
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(side_effect=lambda k: "10" if "total" in k else "3")
        tracker = NXDomainTracker(redis_client=mock_redis)
        ratio = asyncio.run(tracker.get_nxdomain_ratio("1.2.3.4"))
        assert abs(ratio - 0.3) < 0.01

    def test_get_ratio_no_data(self):
        from common.features.nxdomain import NXDomainTracker
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        tracker = NXDomainTracker(redis_client=mock_redis)
        ratio = asyncio.run(tracker.get_nxdomain_ratio("1.2.3.4"))
        assert ratio == 0.0
