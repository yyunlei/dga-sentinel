"""
反馈回灌路由 — 人工标注结果收集
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from business.repositories.pg_repo import get_pg_pool
from business.middleware.rate_limit import rate_limit_check
from business.middleware.rbac import require_analyst
from common.observability import get_logger

logger = get_logger(__name__)

router = APIRouter()

# 延迟导入 Prometheus counter
_feedback_counter = None


def _get_counter():
    global _feedback_counter
    if _feedback_counter is None:
        from prometheus_client import Counter
        _feedback_counter = Counter(
            "dga_feedback_total",
            "Annotation feedback count",
            ["label"],
        )
    return _feedback_counter


class FeedbackRequest(BaseModel):
    event_id: str
    domain: str
    true_label: str          # "dga" / "benign"
    predicted_label: str = ""
    score: float = 0.0
    family: str | None = None  # 预测家族（可选）— 喂给 per-family 阈值推荐器
    annotator: str = "anonymous"


class FeedbackResponse(BaseModel):
    status: str
    event_id: str
    received_at: str


@router.post("/feedback", response_model=FeedbackResponse, dependencies=[Depends(rate_limit_check), Depends(require_analyst)])
async def submit_feedback(req: FeedbackRequest, pg=Depends(get_pg_pool)):
    """接收人工标注反馈"""
    _get_counter().labels(label=req.true_label).inc()
    logger.info(
        "feedback_received",
        event_id=req.event_id,
        domain=req.domain,
        true_label=req.true_label,
        annotator=req.annotator,
    )
    # Write to PG feedback table when available
    if pg:
        try:
            await pg.execute(
                """
                INSERT INTO feedback
                    (event_id, domain, true_label, predicted_label, score, family, annotator)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                req.event_id, req.domain, req.true_label, req.predicted_label,
                req.score, req.family, req.annotator,
            )
        except Exception as e:
            logger.warning("feedback_pg_write_failed", error=str(e))
    return FeedbackResponse(
        status="accepted",
        event_id=req.event_id,
        received_at=datetime.now(timezone.utc).isoformat(),
    )
