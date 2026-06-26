"""EnsembleScorer 单元测试"""

import pytest
from unittest.mock import MagicMock

joblib = pytest.importorskip("joblib")
from ai.scoring.models.ensemble import EnsembleScorer, ScoringResult


class TestEnsembleScorer:
    def _make_scorer(self, weights=None):
        binary = MagicMock()
        binary.version = "v1.0"
        multi = MagicMock()
        multi.version = "v1.0"
        return EnsembleScorer(binary, multi, threshold=0.5, weights=weights), binary, multi

    def test_score_benign(self):
        scorer, binary, multi = self._make_scorer()
        binary.predict.return_value = (0, 0.1)
        result = scorer.score("google.com")
        assert not result.is_dga
        assert result.score == 0.1
        assert result.family is None
        multi.predict.assert_not_called()

    def test_score_dga_above_threshold(self):
        scorer, binary, multi = self._make_scorer()
        binary.predict.return_value = (1, 0.9)
        multi.predict.return_value = [{"family": "qakbot", "confidence": 0.85}]
        result = scorer.score("abc123.xyz")
        assert result.is_dga
        assert result.family == "qakbot"
        assert result.family_confidence == 0.85

    def test_score_dga_below_threshold(self):
        scorer, binary, multi = self._make_scorer()
        binary.predict.return_value = (1, 0.3)
        result = scorer.score("abc.xyz")
        assert result.is_dga
        assert result.family is None
        multi.predict.assert_not_called()

    def test_weighted_fusion(self):
        scorer, binary, multi = self._make_scorer(weights={"binary_weight": 0.6, "multi_weight": 0.4})
        binary.predict.return_value = (1, 0.9)
        multi.predict.return_value = [{"family": "necurs", "confidence": 0.8}]
        result = scorer.score("evil.xyz")
        expected = min(1.0, 0.9 * 0.6 + 0.8 * 0.4)
        assert abs(result.score - expected) < 0.001

    def test_score_batch(self):
        scorer, binary, multi = self._make_scorer()
        binary.predict.return_value = (0, 0.1)
        results = scorer.score_batch(["a.com", "b.com"])
        assert len(results) == 2

    def test_score_batch_parallel(self):
        scorer, binary, multi = self._make_scorer()
        binary.predict.return_value = (0, 0.1)
        results = scorer.score_batch_parallel(["a.com", "b.com"], max_workers=2)
        assert len(results) == 2
