"""
评分客户端节点 — 调用 ScoringService（gRPC 或 HTTP）
"""

from __future__ import annotations

import os

from typing import Any

import httpx

from dag_engine.nodes.base import BaseNode, logger


class ScoringClientNode(BaseNode):
    """调用评分服务进行模型推理"""

    node_type = "scoring_service"

    async def process(self, state: dict[str, Any]) -> dict[str, Any]:
        domain = state.get("domain", "")
        if not domain:
            return state

        endpoint = self.config.get("endpoint") or os.environ.get("SCORING_SERVICE_ENDPOINT", "http://scoring-service:8001")
        protocol = self.config.get("protocol", "http")
        timeout_ms = self.config.get("timeout_ms", 3000)
        tenant_id = state.get("tenant_id", "default")

        if protocol == "http":
            result = await self._score_http(domain, endpoint, timeout_ms, tenant_id)
        else:
            # gRPC 调用（后续实现）
            result = await self._score_http(domain, endpoint, timeout_ms, tenant_id)

        state["score"] = result.get("score", 0.0)
        state["is_dga"] = result.get("is_dga", False)
        state["family"] = result.get("family")
        state["family_confidence"] = result.get("family_confidence")
        state["model_version"] = result.get("model_version", "")
        return state

    async def _score_http(self, domain: str, endpoint: str, timeout_ms: int, tenant_id: str) -> dict:
        """通过 HTTP 调用评分服务"""
        url = f"{endpoint}/score"
        try:
            async with httpx.AsyncClient(timeout=timeout_ms / 1000) as client:
                resp = await client.post(url, json={"domains": [domain], "tenant_id": tenant_id})
                resp.raise_for_status()
                data = resp.json()
                if data.get("results"):
                    return data["results"][0]
                return {}
        except Exception as e:
            logger.warning("scoring_call_failed", domain=domain, error=str(e))
            return {"score": 0.0, "is_dga": False}
