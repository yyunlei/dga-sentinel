"""
评分路由 — /score /score/batch
评分完成后将符合条件的结果写入 ES，供告警中心展示真实数据。
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime, timezone
from uuid import uuid4

import httpx
from elasticsearch import AsyncElasticsearch
from fastapi import APIRouter, Depends, HTTPException, Request

from shared.schemas import ScoreRequest, ScoreResponse, ScoreResult
from shared.config import get_settings
from shared.constants import ES_INDEX_EVENTS
from shared.observability import SCORE_REQUESTS
from gateway.middleware.rate_limit import rate_limit_check
from gateway.middleware.auth import verify_token
from gateway.middleware.rbac import require_analyst
from gateway.db import get_es_client, get_redis_client
from gateway.starrocks_client import write_events_to_starrocks

router = APIRouter()

# 分数 -> 严重度
def _score_to_severity(score: float) -> str:
    if score >= 0.9:
        return "CRITICAL"
    if score >= 0.7:
        return "HIGH"
    if score >= 0.5:
        return "MEDIUM"
    return "LOW"

# 宽松校验：允许常见域名格式（含单标签如 test）
_DOMAIN_RE = re.compile(r"^[a-zA-Z0-9]([a-zA-Z0-9._-]*[a-zA-Z0-9])?$")
_MAX_DOMAIN_LEN = 253
_MAX_BATCH_SIZE = 1000


def _validate_domains(domains: list[str]) -> list[str]:
    """校验域名输入，过滤非法项而非直接 400，保证至少有一项有效"""
    if len(domains) > _MAX_BATCH_SIZE:
        raise HTTPException(400, detail=f"Batch size exceeds limit ({_MAX_BATCH_SIZE})")
    validated = []
    for d in domains:
        if not isinstance(d, str):
            continue
        d = d.strip().lower()
        if not d:
            continue
        if len(d) > _MAX_DOMAIN_LEN:
            continue
        # 允许字母数字、点、横线、下划线
        if _DOMAIN_RE.match(d):
            validated.append(d)
    return validated


@router.post("/score", response_model=ScoreResponse, dependencies=[Depends(rate_limit_check), Depends(require_analyst)])
async def score_domains(
    req: ScoreRequest,
    request: Request,
    es: AsyncElasticsearch | None = Depends(get_es_client),
    redis_client=Depends(get_redis_client),
):
    """单个/批量域名评分 — 转发到 ScoringService，并将命中结果写入 ES 供告警中心展示"""
    settings = get_settings()
    trace_id = getattr(request.state, "trace_id", uuid4().hex)
    start = time.perf_counter()

    validated = _validate_domains(req.domains)
    if not validated:
        return ScoreResponse(trace_id=trace_id, results=[], latency_ms=0)

    # Redis cache: check for cached scores
    cached_results: list[ScoreResult] = []
    uncached_domains: list[str] = []
    for domain in validated:
        domain_hash = hashlib.sha256(domain.encode()).hexdigest()[:16]
        cache_key = f"score:{domain_hash}"
        if redis_client:
            try:
                cached = await redis_client.get(cache_key)
                if cached:
                    cached_results.append(ScoreResult(**json.loads(cached)))
                    continue
            except Exception:
                pass
        uncached_domains.append(domain)

    # Score uncached domains via scoring service
    new_results: list[ScoreResult] = []
    if uncached_domains:
        scoring_url = f"http://{settings.scoring_host}:{settings.scoring_http_port}/score"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(scoring_url, json={"domains": uncached_domains, "tenant_id": req.tenant_id})
                resp.raise_for_status()
                data = resp.json()
            new_results = [ScoreResult(**r) for r in data.get("results", [])]
            # Cache new results in Redis (TTL=300s)
            if redis_client:
                for r in new_results:
                    domain_hash = hashlib.sha256(r.domain.encode()).hexdigest()[:16]
                    cache_key = f"score:{domain_hash}"
                    try:
                        cache_data = r.model_dump()
                        cache_data["cached"] = True
                        await redis_client.set(cache_key, json.dumps(cache_data), ex=300)
                    except Exception:
                        pass
        except httpx.HTTPError:
            pass

    results = cached_results + new_results
    for r in results:
        SCORE_REQUESTS.labels(endpoint="/score", tenant_id=req.tenant_id).inc()

    # 将符合条件的结果写入 ES 与 StarRocks（is_dga 或 score >= 0.7）
    to_store = [r for r in results if r.is_dga or r.score >= 0.7]
    utc_now = datetime.now(timezone.utc)
    es_docs = []
    starrocks_rows = []
    for r in to_store:
        event_id = str(uuid4())
        severity = _score_to_severity(r.score)
        ts_iso = utc_now.isoformat().replace("+00:00", "Z")
        ts_datetime = utc_now.strftime("%Y-%m-%d %H:%M:%S")
        es_docs.append((event_id, {
            "event_id": event_id,
            "trace_id": trace_id,
            "timestamp": ts_iso,
            "domain": r.domain,
            "src_ip": "",
            "score": r.score,
            "is_dga": r.is_dga,
            "family": r.family,
            "family_confidence": r.family_confidence,
            "model_version": r.model_version or "",
            "pipeline_id": "gateway",
            "severity": severity,
            "acknowledged": False,
            "tenant_id": req.tenant_id,
        }))
        starrocks_rows.append({
            "event_id": event_id,
            "trace_id": trace_id,
            "event_time": ts_datetime,
            "domain": r.domain,
            "src_ip": "",
            "score": float(r.score),
            "is_dga": bool(r.is_dga),
            "family": r.family or "",
            "family_confidence": float(r.family_confidence or 0),
            "model_version": r.model_version or "",
            "pipeline_id": "gateway",
            "tenant_id": req.tenant_id,
            "severity": severity,
        })

    if es and es_docs:
        now = utc_now.strftime("%Y.%m.%d")
        index = f"{ES_INDEX_EVENTS}-{now}"
        for event_id, doc in es_docs:
            try:
                await es.index(index=index, document=doc, id=event_id)
            except Exception:
                pass

    if starrocks_rows:
        await write_events_to_starrocks(starrocks_rows)

    latency_ms = (time.perf_counter() - start) * 1000
    return ScoreResponse(trace_id=trace_id, results=results, latency_ms=latency_ms)
