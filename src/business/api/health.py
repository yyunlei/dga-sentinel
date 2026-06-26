"""
健康检查路由 — /healthz /readyz /metrics
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import JSONResponse, Response
import httpx

from business.infra.connections import get_redis_client, get_pg_pool, get_es_client

router = APIRouter()


@router.get("/healthz")
async def healthz():
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(
    redis=Depends(get_redis_client),
    pg_pool=Depends(get_pg_pool),
    es_client=Depends(get_es_client),
):
    checks: dict[str, str] = {}

    # PostgreSQL check
    try:
        if pg_pool:
            await pg_pool.fetchval("SELECT 1")
            checks["postgres"] = "ok"
        else:
            checks["postgres"] = "no_pool"
    except Exception as e:
        checks["postgres"] = f"failed: {e}"

    # Redis check
    try:
        if redis:
            await redis.ping()
            checks["redis"] = "ok"
        else:
            checks["redis"] = "no_client"
    except Exception as e:
        checks["redis"] = f"failed: {e}"

    # Elasticsearch check
    try:
        if es_client:
            info = await es_client.info()
            checks["elasticsearch"] = f"ok (v{info['version']['number']})"
        else:
            checks["elasticsearch"] = "no_client"
    except Exception as e:
        checks["elasticsearch"] = f"failed: {e}"

    # Scoring service check
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get("http://scoring-service:8001/healthz", timeout=3)
            checks["scoring"] = "ok" if resp.status_code == 200 else "failed"
    except Exception:
        checks["scoring"] = "failed"

    # OpenTelemetry / Jaeger check
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get("http://jaeger:16686/api/services", timeout=3)
            checks["jaeger"] = "ok" if resp.status_code == 200 else "failed"
    except Exception:
        checks["jaeger"] = "unreachable"

    failed = [k for k, v in checks.items() if not v.startswith("ok")]
    if failed:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "checks": checks},
        )
    return {"status": "ready", "checks": checks}


@router.get("/metrics")
async def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
