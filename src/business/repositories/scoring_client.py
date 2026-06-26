"""
评分服务 HTTP 客户端 — 封装对 scoring-service /score 的 HTTP 调用。
业务逻辑不在此处；降级行为（HTTP 错误 → 空列表）保持与原 score.py 一致。
"""
from __future__ import annotations

import httpx

from common.schemas import ScoreResult


class ScoringClient:
    """HTTP client for the scoring micro-service /score endpoint."""

    def __init__(self, scoring_url: str, timeout: float = 5.0) -> None:
        self._scoring_url = scoring_url
        self._timeout = timeout

    async def score(self, domains: list[str], tenant_id: str) -> list[ScoreResult]:
        """
        发送域名列表到 scoring-service，返回 ScoreResult 列表。
        HTTP 错误时静默降级返回空列表（与原 score.py 行为一致）。
        """
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    self._scoring_url,
                    json={"domains": domains, "tenant_id": tenant_id},
                )
                resp.raise_for_status()
                data = resp.json()
            return [ScoreResult(**r) for r in data.get("results", [])]
        except httpx.HTTPError:
            return []
