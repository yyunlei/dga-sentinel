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
    def test_matrix_stats_keys(self):
        """_matrix_stats returns 7 statistical keys with correct prefix"""
        sparse = pytest.importorskip("scipy.sparse")
        from common.features.ngram import NgramFeatureExtractor
        matrix = sparse.csr_matrix(np.array([[1, 2, 3, 4, 5]]))
        result = NgramFeatureExtractor._matrix_stats(matrix, "test")
        # Production code returns: mean, var, min, std, max, skew, kurtosis (no median)
        expected_keys = {"test_mean", "test_std", "test_var", "test_min", "test_max", "test_skew", "test_kurtosis"}
        assert set(result.keys()) == expected_keys

    def test_extract_returns_21_features(self):
        sparse = pytest.importorskip("scipy.sparse")
        from common.features.ngram import NgramFeatureExtractor
        with patch.object(NgramFeatureExtractor, "__init__", return_value=None):
            extractor = NgramFeatureExtractor()
            mock_vec = MagicMock()
            mock_vec.transform.return_value = sparse.csr_matrix(np.array([[0.1, 0.2, 0.3]]))
            # Production extract() uses self.unigrams / self.bigrams / self.trigrams
            extractor.unigrams = mock_vec
            extractor.bigrams = mock_vec
            extractor.trigrams = mock_vec
            result = extractor.extract("example.com")
            assert len(result) == 21
            # Keys follow UNI-*/BI-*/TRI-* naming convention
            for prefix in ("UNI", "BI", "TRI"):
                for stat in ("MEAN", "VAR", "PVAR", "STD", "PSTD", "SKE", "KUR"):
                    assert f"{prefix}-{stat}" in result


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
