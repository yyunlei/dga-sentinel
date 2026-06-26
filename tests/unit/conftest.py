"""
Unit-test 环境 stub 注入(仅在真实包缺失时生效)。

**为什么需要它:** 本仓库的本地测试 venv 是精简环境(httpx / elasticsearch /
redis 等已装,但 pydantic / pydantic_settings / prometheus_client / structlog
未装,因为完整 `uv sync` 会拉 TensorFlow,在 Intel-Mac 上无 wheel)。本 conftest
让 service 层单测(detection_service / scoring_client 等)能在精简 venv 里被导入。

**可信度保证(关键):** 每个 stub 仅在 `importlib.util.find_spec(name) is None`
(即该包真不存在)时才注入。所以:
- **Docker / CI / 完整 venv**:真实 pydantic 等存在 → 不注入 stub → 测试跑在
  真实实现上,字段校验/序列化语义完整,结果可信。
- **本地精简 venv**:真包缺失 → 注入最小 duck-type stub → 仅验证 service 的
  **编排逻辑**(用 fake repo),不验证 pydantic 字段校验。

service 单测的目的本就是验证编排逻辑;pydantic 校验/端到端正确性由容器冲烟覆盖。
若某天本地装上了真包,这些 stub 自动让位,无需改动。
"""
from __future__ import annotations

import importlib.util
import sys
import types


def _install_stub(name: str, module: types.ModuleType) -> None:
    """仅当真实包不存在时,把 stub 注册到 sys.modules(真包存在则原样保留)。"""
    if importlib.util.find_spec(name) is None:
        sys.modules[name] = module


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
_install_stub("pydantic", _pydantic)

# ---------------------------------------------------------------------------
# pydantic_settings stub (needed if any path transitively imports common.config)
# ---------------------------------------------------------------------------

_ps = types.ModuleType("pydantic_settings")
_ps.BaseSettings = _BaseModel
_ps.SettingsConfigDict = dict
_install_stub("pydantic_settings", _ps)

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
_install_stub("prometheus_client", _prom)

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
_install_stub("structlog", _structlog)
