"""
评分路由 — /score
HTTP 层：解析请求 → 校验域名 → 调 DetectionService → 包装响应。
不包含缓存/评分/事件写入逻辑，均委托给 DetectionService。
"""
from __future__ import annotations

import re
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from elasticsearch import AsyncElasticsearch

from common.schemas import ScoreRequest, ScoreResponse
from common.config import get_settings
from business.middleware.rate_limit import rate_limit_check
from business.middleware.rbac import require_analyst
from business.repositories.pg_repo import get_es_client, get_redis_client
from business.repositories.starrocks_repo import write_events_to_starrocks
from business.repositories.scoring_client import ScoringClient
from business.services.detection_service import DetectionService

router = APIRouter()

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


def _service(
    es: AsyncElasticsearch | None = Depends(get_es_client),
    redis_client=Depends(get_redis_client),
) -> DetectionService:
    """DI 工厂：注入依赖 → DetectionService。"""
    settings = get_settings()
    scoring_url = (
        f"http://{settings.scoring_host}:{settings.scoring_http_port}/score"
    )
    return DetectionService(
        scoring_client=ScoringClient(scoring_url=scoring_url),
        es=es,
        redis_client=redis_client,
        write_events_fn=write_events_to_starrocks,
    )


@router.post(
    "/score",
    response_model=ScoreResponse,
    dependencies=[Depends(rate_limit_check), Depends(require_analyst)],
)
async def score_domains(
    req: ScoreRequest,
    request: Request,
    svc: DetectionService = Depends(_service),
):
    """单个/批量域名评分 — 转发到 ScoringService，并将命中结果写入 ES 供告警中心展示"""
    trace_id = getattr(request.state, "trace_id", uuid4().hex)

    validated = _validate_domains(req.domains)
    if not validated:
        return ScoreResponse(trace_id=trace_id, results=[], latency_ms=0)

    results, latency_ms = await svc.score_domains(req, validated, trace_id)
    return ScoreResponse(trace_id=trace_id, results=results, latency_ms=latency_ms)
