"""
Unit-test 环境 stub 注入。

测试运行的 venv 仅包含精简依赖（httpx、elasticsearch、redis 等），
不包含 pydantic、prometheus_client、structlog。
此 conftest.py 在 pytest 收集测试模块之前向 sys.modules 注入最小可用 stub，
使得 detection_service / scoring_client 等模块可被正常导入。

已有的通过测试（test_alert_service 等）不依赖这些包，setdefault 不会覆盖已存在的模块。
"""
from __future__ import annotations

import sys
import types


# ---------------------------------------------------------------------------
# pydantic stub
# ---------------------------------------------------------------------------

class _BaseModel:
    """Minimal pydantic.BaseModel duck-type: stores kwargs as instance attrs."""

    def __init__(self, **kwargs):  # noqa: D107
        for k, v in kwargs.items():
            setattr(self, k, v)

    def model_dump(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}


def _Field(*args, **kwargs):
    """pydantic.Field stub — returns the 'default' kwarg or None."""
    return kwargs.get("default", None)


_pydantic = types.ModuleType("pydantic")
_pydantic.BaseModel = _BaseModel
_pydantic.Field = _Field
_pydantic.model_validator = lambda *a, **kw: (lambda f: f)  # no-op decorator
sys.modules.setdefault("pydantic", _pydantic)

# ---------------------------------------------------------------------------
# pydantic_settings stub (needed if any path transitively imports common.config)
# ---------------------------------------------------------------------------

_ps = types.ModuleType("pydantic_settings")
_ps.BaseSettings = _BaseModel
_ps.SettingsConfigDict = dict
sys.modules.setdefault("pydantic_settings", _ps)

# ---------------------------------------------------------------------------
# prometheus_client stub
# ---------------------------------------------------------------------------

class _Metric:
    def __init__(self, *a, **kw):
        pass

    def labels(self, **kw):
        return self

    def inc(self, n: float = 1) -> None:
        pass

    def observe(self, v: float) -> None:
        pass

    def set(self, v: float) -> None:
        pass


_prom = types.ModuleType("prometheus_client")
_prom.Counter = _Metric
_prom.Histogram = _Metric
_prom.Gauge = _Metric
sys.modules.setdefault("prometheus_client", _prom)

# ---------------------------------------------------------------------------
# structlog stub
# ---------------------------------------------------------------------------

class _Logger:
    def info(self, *a, **kw):
        pass

    def error(self, *a, **kw):
        pass

    def debug(self, *a, **kw):
        pass

    def warning(self, *a, **kw):
        pass


_structlog = types.ModuleType("structlog")
_structlog.get_logger = lambda *a, **kw: _Logger()
sys.modules.setdefault("structlog", _structlog)
