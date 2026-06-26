"""
DGA Platform — API 网关
统一入口：评分、解释、告警、模型管理、DAG 管理、健康检查
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response

from shared.config import get_settings
from shared.observability import setup_logging, get_logger
from gateway.middleware.tracing import TracingMiddleware
from gateway.middleware.security import SecurityHeadersMiddleware
from gateway.middleware.audit import AuditMiddleware
from gateway.db import init_db, close_db
from gateway.routers import score, health, alerts, models, dag, explain, feedback, realtime, query, node_configs, agents, dashboard, reports, rag, operations

logger = get_logger(__name__)


def _instrument_otel(app: FastAPI, settings) -> None:
    """Wire up OpenTelemetry auto-instrumentation for FastAPI + asyncpg + httpx."""
    if not settings.otel_endpoint:
        return
    try:
        from shared.observability import setup_tracing
        setup_tracing("gateway", settings.otel_endpoint)
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        FastAPIInstrumentor.instrument_app(app)
        logger.info("otel_fastapi_instrumented")
        try:
            from opentelemetry.instrumentation.asyncpg import AsyncPGInstrumentor
            AsyncPGInstrumentor().instrument()
            logger.info("otel_asyncpg_instrumented")
        except Exception:
            pass
        try:
            from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
            HTTPXClientInstrumentor().instrument()
            logger.info("otel_httpx_instrumented")
        except Exception:
            pass
    except Exception as e:
        logger.warning("otel_instrument_failed", error=str(e))


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging(settings.log_level, json_output=not settings.is_dev)
    _instrument_otel(app, settings)
    await init_db(app)
    logger.info("gateway_starting", env=settings.app_env)
    yield
    await close_db(app)
    logger.info("gateway_shutdown")


app = FastAPI(
    title="DGA Threat Detection Platform",
    version="0.1.0",
    description="DGA 智能威胁检测平台 API 网关",
    lifespan=lifespan,
)

# CORS
import os as _os
_cors_origins = _os.environ.get("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors_origins],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# trace_id 中间件
app.add_middleware(TracingMiddleware)

# 安全头中间件
app.add_middleware(SecurityHeadersMiddleware)

# 审计日志中间件
app.add_middleware(AuditMiddleware)

# 注册路由（前缀 /api，与 nginx 转发 /api/ 到 gateway 时保留路径一致）
app.include_router(score.router, prefix="/api", tags=["Scoring"])
app.include_router(explain.router, prefix="/api", tags=["Explain"])
app.include_router(alerts.router, prefix="/api", tags=["Alerts"])
app.include_router(models.router, prefix="/api", tags=["Models"])
app.include_router(dag.router, prefix="/api", tags=["DAG"])
app.include_router(health.router, prefix="/api", tags=["Health"])
app.include_router(feedback.router, prefix="/api", tags=["Feedback"])
app.include_router(realtime.router, prefix="/api", tags=["Realtime"])
app.include_router(query.router, prefix="/api", tags=["Query"])
app.include_router(node_configs.router, prefix="/api", tags=["NodeConfigs"])
app.include_router(agents.router, prefix="/api", tags=["Agents"])
app.include_router(dashboard.router, prefix="/api", tags=["Dashboard"])
app.include_router(reports.router, prefix="/api", tags=["Reports"])
app.include_router(rag.router, prefix="/api", tags=["RAG"])
app.include_router(operations.router, prefix="/api", tags=["Operations"])

# 根级别健康检查（供 Docker/K8s 探针使用）
@app.get("/health")
async def root_health():
    return {"status": "ok"}