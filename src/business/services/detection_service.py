"""
域名检测业务编排 — DetectionService。
不依赖 FastAPI；依赖通过构造函数注入，可独立单测。

职责：
  score_domains — Redis 缓存检查 → ScoringClient → 写缓存 → 写 ES + StarRocks 事件
  query_data   — 转发自然语言查询到 agent-layer
"""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from uuid import uuid4

import httpx

from common.schemas import ScoreRequest, ScoreResult
from common.constants import ES_INDEX_EVENTS
from common.observability import SCORE_REQUESTS
from business.repositories.scoring_client import ScoringClient


def _score_to_severity(score: float) -> str:
    if score >= 0.9:
        return "CRITICAL"
    if score >= 0.7:
        return "HIGH"
    if score >= 0.5:
        return "MEDIUM"
    return "LOW"


class DetectionService:
    """域名检测业务编排：缓存→评分→写缓存→写事件；以及自然语言查询编排。"""

    def __init__(
        self,
        *,
        scoring_client: ScoringClient | None = None,
        es=None,
        redis_client=None,
        write_events_fn=None,
        agent_layer_url: str = "http://agent-layer:8002",
    ) -> None:
        self._scoring_client = scoring_client
        self._es = es
        self._redis = redis_client
        self._write_events = write_events_fn
        self._agent_layer_url = agent_layer_url

    # ------------------------------------------------------------------
    # 评分与事件写入
    # ------------------------------------------------------------------

    async def score_domains(
        self,
        req: ScoreRequest,
        validated: list[str],
        trace_id: str,
    ) -> tuple[list[ScoreResult], float]:
        """
        缓存检查 → 调 ScoringClient → 写缓存 → 写 ES / StarRocks 事件。
        返回 (results, latency_ms)。
        """
        start = time.perf_counter()

        # Redis cache: check for cached scores
        cached_results: list[ScoreResult] = []
        uncached_domains: list[str] = []
        for domain in validated:
            domain_hash = hashlib.sha256(domain.encode()).hexdigest()[:16]
            cache_key = f"score:{domain_hash}"
            if self._redis:
                try:
                    cached = await self._redis.get(cache_key)
                    if cached:
                        cached_results.append(ScoreResult(**json.loads(cached)))
                        continue
                except Exception:
                    pass
            uncached_domains.append(domain)

        # Score uncached domains via scoring service
        new_results: list[ScoreResult] = []
        if uncached_domains and self._scoring_client:
            new_results = await self._scoring_client.score(
                uncached_domains, req.tenant_id
            )
            # Cache new results in Redis (TTL=300s)
            if self._redis:
                for r in new_results:
                    domain_hash = hashlib.sha256(r.domain.encode()).hexdigest()[:16]
                    cache_key = f"score:{domain_hash}"
                    try:
                        cache_data = r.model_dump()
                        cache_data["cached"] = True
                        await self._redis.set(
                            cache_key, json.dumps(cache_data), ex=300
                        )
                    except Exception:
                        pass

        results = cached_results + new_results
        for r in results:
            SCORE_REQUESTS.labels(endpoint="/score", tenant_id=req.tenant_id).inc()

        # 将符合条件的结果写入 ES 与 StarRocks（is_dga 或 score >= 0.7）
        to_store = [r for r in results if r.is_dga or r.score >= 0.7]
        utc_now = datetime.now(timezone.utc)
        es_docs: list[tuple[str, dict]] = []
        starrocks_rows: list[dict] = []
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

        if self._es and es_docs:
            now = utc_now.strftime("%Y.%m.%d")
            index = f"{ES_INDEX_EVENTS}-{now}"
            for event_id, doc in es_docs:
                try:
                    await self._es.index(index=index, document=doc, id=event_id)
                except Exception:
                    pass

        if starrocks_rows and self._write_events:
            await self._write_events(starrocks_rows)

        latency_ms = (time.perf_counter() - start) * 1000
        return results, latency_ms

    # ------------------------------------------------------------------
    # 自然语言查询（转发到 agent-layer）
    # ------------------------------------------------------------------

    async def query_data(
        self,
        question: str,
        db_type: str,
        trace_id: str,
    ) -> dict:
        """
        自然语言查询 → agent-layer HTTP dispatch。
        HTTP 错误时抛出原始 httpx 异常，由调用方转换为 HTTPException。
        """
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self._agent_layer_url}/query",
                json={"question": question, "db_type": db_type},
            )
            resp.raise_for_status()
            result = resp.json()
        return {
            "sql": result.get("sql", ""),
            "data": result.get("data", []),
            "explanation": result.get("explanation", ""),
            "error": result.get("error"),
            "trace_id": trace_id,
        }
