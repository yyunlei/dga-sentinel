"""评分 API 集成测试"""

import sys
import pytest
from unittest.mock import patch, MagicMock

fastapi = pytest.importorskip("fastapi")

# Pre-mock heavy ML dependencies before any scoring_service imports
_tf_mock = MagicMock()
_MOCK_MODULES = {
    "tensorflow": _tf_mock,
    "tensorflow.keras": _tf_mock.keras,
    "tensorflow.keras.models": _tf_mock.keras.models,
    "tensorflow.keras.preprocessing": _tf_mock.keras.preprocessing,
    "tensorflow.keras.preprocessing.sequence": _tf_mock.keras.preprocessing.sequence,
}
for _mod, _mock in _MOCK_MODULES.items():
    sys.modules.setdefault(_mod, _mock)

try:
    import joblib  # noqa: F401
except ImportError:
    sys.modules.setdefault("joblib", MagicMock())

try:
    from scipy import stats  # noqa: F401
except ImportError:
    _scipy = MagicMock()
    sys.modules.setdefault("scipy", _scipy)
    sys.modules.setdefault("scipy.stats", _scipy.stats)


class TestScoringAPI:
    """测试评分服务 HTTP 端点（使用 mock 模型）"""

    def test_healthz(self):
        """健康检查端点"""
        from scoring_service.main import app
        from fastapi.testclient import TestClient

        with patch("scoring_service.main._scorer", MagicMock()):
            client = TestClient(app)
            resp = client.get("/healthz")
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"

    def test_readyz_not_ready(self):
        """就绪检查 — 模型未加载"""
        from scoring_service.main import app
        from fastapi.testclient import TestClient

        with patch("scoring_service.main._scorer", None):
            client = TestClient(app)
            resp = client.get("/readyz")
            assert resp.status_code == 503

    def test_metrics(self):
        """Prometheus 指标端点"""
        from scoring_service.main import app
        from fastapi.testclient import TestClient

        with patch("scoring_service.main._scorer", MagicMock()):
            client = TestClient(app)
            resp = client.get("/metrics")
            assert resp.status_code == 200
            assert "dga_score_requests_total" in resp.text
