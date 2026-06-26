"""
DGA Scoring Service — FastAPI + gRPC 双协议评分服务
独立部署，供 DAG 引擎和 API 网关调用
"""

from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from pydantic import BaseModel
from starlette.responses import Response

from shared.config import get_settings
from shared.schemas import ScoreRequest, ScoreResponse, ScoreResult
from shared.observability import (
    setup_logging, get_logger, SCORE_REQUESTS, SCORE_LATENCY, DGA_HITS,
)
from shared.constants import DEFAULT_DGA_THRESHOLD
from scoring_service.models.binary_model import BinaryModel
from scoring_service.models.multi_model import MultiClassModel
from scoring_service.models.ensemble import EnsembleScorer
from scoring_service.models.registry import ModelRegistry, ModelEntry
from scoring_service.drift import DriftMonitor

logger = get_logger(__name__)

# ── 全局状态 ──────────────────────────────────────────
_registry = ModelRegistry()
_scorer: EnsembleScorer | None = None

# Drift 监控状态
_drift: DriftMonitor | None = None
_drift_pg_pool = None
_drift_task: asyncio.Task | None = None
DRIFT_CHECK_INTERVAL_SEC = 300  # 5 分钟


def _load_models() -> EnsembleScorer:
    """加载模型并注册"""
    settings = get_settings()
    project_root = Path(__file__).resolve().parent.parent

    binary_path = project_root / settings.model_binary_path
    multi_path = project_root / settings.model_multi_path

    binary_model = BinaryModel(str(binary_path))
    multi_model = MultiClassModel(str(multi_path))

    _registry.register(ModelEntry(
        model_id="binary-xgboost", version=binary_model.version,
        artifact_path=str(binary_path), status="production", instance=binary_model,
    ))
    _registry.register(ModelEntry(
        model_id="multi-cnn-attention", version=multi_model.version,
        artifact_path=str(multi_path), status="production", instance=multi_model,
    ))

    logger.info("models_loaded", binary=str(binary_path), multi=str(multi_path))
    return EnsembleScorer(binary_model, multi_model, threshold=DEFAULT_DGA_THRESHOLD)


async def _try_init_drift_pg_pool(pg_dsn: str, attempts: int = 8):
    """Best-effort PG pool init with short retries. Returns None on terminal failure."""
    import asyncpg
    last_err: Exception | None = None
    for i in range(attempts):
        try:
            pool = await asyncpg.create_pool(pg_dsn, min_size=1, max_size=2)
            logger.info("drift_pg_pool_ready", attempt=i + 1)
            return pool
        except Exception as e:  # noqa: BLE001
            last_err = e
            await asyncio.sleep(2)
    logger.warning("drift_pg_pool_unavailable", error=str(last_err) if last_err else "unknown")
    return None


async def _ensure_drift_pg_pool():
    """端点 lazy-init 兜底：lifespan 阶段没拿到 pool 时，由首次 /drift/persist 触发。"""
    global _drift_pg_pool
    if _drift_pg_pool is not None:
        return _drift_pg_pool
    settings = get_settings()
    _drift_pg_pool = await _try_init_drift_pg_pool(settings.pg_dsn, attempts=3)
    return _drift_pg_pool


async def _drift_periodic_check() -> None:
    """每 5 分钟跑一次：check_drift + 把 PSI ≥ 阈值的 feature 持久化到 PG。"""
    while True:
        try:
            await asyncio.sleep(DRIFT_CHECK_INTERVAL_SEC)
            if _drift is None:
                continue
            scores = _drift.check_drift()
            if not scores:
                logger.debug("drift_check_skip", reason="no baseline or window too small")
                continue
            if _drift_pg_pool is not None:
                written = await _drift.persist_drift_alerts(_drift_pg_pool, scores)
                if written:
                    logger.info("drift_alerts_persisted", count=written)
        except asyncio.CancelledError:
            logger.info("drift_periodic_check_stopping")
            break
        except Exception as e:  # noqa: BLE001
            logger.error("drift_periodic_check_error", error=str(e))


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _scorer, _drift, _drift_pg_pool, _drift_task
    settings = get_settings()
    setup_logging(settings.log_level, json_output=not settings.is_dev)
    from shared.observability import setup_tracing
    setup_tracing("scoring-service", settings.otel_endpoint)
    logger.info("scoring_service_starting")
    _scorer = _load_models()

    # Drift 监控初始化（best-effort，PG 不可用不阻塞启动）
    _drift = DriftMonitor(window_size=1000)
    _drift_pg_pool = await _try_init_drift_pg_pool(settings.pg_dsn)
    _drift_task = asyncio.create_task(_drift_periodic_check())

    from scoring_service.grpc_server import start_grpc_server
    grpc_server = start_grpc_server(_scorer)
    logger.info("scoring_service_ready")
    yield

    if _drift_task is not None:
        _drift_task.cancel()
        try:
            await _drift_task
        except asyncio.CancelledError:
            pass
    if _drift_pg_pool is not None:
        await _drift_pg_pool.close()
    grpc_server.stop(grace=5)
    logger.info("scoring_service_shutdown")


app = FastAPI(
    title="DGA Scoring Service",
    version="0.1.0",
    lifespan=lifespan,
)


# ── API 端点 ──────────────────────────────────────────

@app.post("/score", response_model=ScoreResponse)
async def score_domains(req: ScoreRequest):
    """单个/批量域名评分"""
    if _scorer is None:
        raise HTTPException(503, "Models not loaded")

    trace_id = uuid4().hex
    start = time.perf_counter()

    results = []
    for domain in req.domains:
        SCORE_REQUESTS.labels(endpoint="/score", tenant_id=req.tenant_id).inc()
        with SCORE_LATENCY.labels(model_version=_scorer.binary.version).time():
            sr = _scorer.score(domain)

        result = ScoreResult(
            domain=sr.domain,
            score=sr.score,
            is_dga=sr.is_dga,
            family=sr.family,
            family_confidence=sr.family_confidence,
            model_version=sr.model_version,
        )
        results.append(result)

        if sr.is_dga:
            DGA_HITS.labels(family=sr.family or "unknown", severity="MEDIUM").inc()

        # Drift 记录（best-effort，绝不阻塞 scoring）
        if _drift is not None:
            try:
                _drift.record({
                    "score": float(sr.score),
                    "domain_len": float(len(domain)),
                })
            except Exception:  # noqa: BLE001
                pass

    latency_ms = (time.perf_counter() - start) * 1000
    return ScoreResponse(trace_id=trace_id, results=results, latency_ms=latency_ms)


@app.get("/healthz")
async def healthz():
    return {"status": "ok", "models_loaded": _scorer is not None}


@app.get("/readyz")
async def readyz():
    if _scorer is None:
        raise HTTPException(503, "Not ready")
    return {"status": "ready"}


@app.get("/metrics")
async def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/models")
async def list_models():
    return _registry.list_models()


# ── Drift 监控端点 (Phase 2) ─────────────────────────


class _DriftBaselineRequest(BaseModel):
    samples: list[dict[str, float]]


class _DriftRecordRequest(BaseModel):
    samples: list[dict[str, float]]


@app.get("/drift/scores")
async def get_drift_scores():
    """返回当前窗口 vs 基线的 PSI 分数（每个 feature 一个）。"""
    if _drift is None:
        raise HTTPException(503, "Drift monitor not initialized")
    return {
        "scores": _drift.check_drift(),
        "window_size": len(_drift._window),
        "baseline_set": _drift._baseline is not None,
    }


@app.post("/drift/baseline")
async def set_drift_baseline(req: _DriftBaselineRequest):
    """设置基线分布（一般取自训练集或上线后稳定窗口）。"""
    if _drift is None:
        raise HTTPException(503, "Drift monitor not initialized")
    _drift.set_baseline(req.samples)
    return {"status": "ok", "n_samples": len(req.samples)}


@app.post("/drift/record")
async def record_drift_samples(req: _DriftRecordRequest):
    """批量喂样本到滑动窗口（测试 / 离线评估用；生产路径走 /score 自动记录）。"""
    if _drift is None:
        raise HTTPException(503, "Drift monitor not initialized")
    for s in req.samples:
        _drift.record(s)
    return {"status": "ok", "added": len(req.samples), "window_size": len(_drift._window)}


@app.post("/drift/persist")
async def persist_drift():
    """立即跑一次 check_drift + 把 PSI ≥ 0.25 的 feature 写入 PG（供 e2e 测试触发）。"""
    if _drift is None:
        raise HTTPException(503, "Drift monitor not initialized")
    pool = await _ensure_drift_pg_pool()
    if pool is None:
        raise HTTPException(503, "Drift PG pool unavailable")
    scores = _drift.check_drift()
    written = await _drift.persist_drift_alerts(pool, scores)
    return {"scores": scores, "alerts_written": written}
