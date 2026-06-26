"""
解释路由 — /explain
通过 HTTP dispatch 调用 agent-layer ExplainAgent 生成域名检测解释
"""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from business.middleware.auth import verify_token
from business.middleware.rbac import require_analyst
from common.config import get_settings
from common.observability import get_logger

router = APIRouter()
logger = get_logger(__name__)

AGENT_LAYER_URL = "http://agent-layer:8002"


class ExplainRequest(BaseModel):
    domain: str
    score: float | None = None
    family: str | None = None
    src_ip: str | None = None


class ExplainResponse(BaseModel):
    domain: str
    explanation: str
    dimensions: list[dict] = []
    confidence: float = 0.0
    trace_id: str = ""


@router.post("/explain", response_model=ExplainResponse, dependencies=[Depends(require_analyst)])
async def explain_domain(req: ExplainRequest, request: Request):
    """通过 pipeline dispatch 触发链式调用: triage → explain + threat_intel → response"""
    trace_id = getattr(request.state, "trace_id", "")

    payload = {"domain": req.domain}
    if req.score is not None:
        payload["score"] = req.score
    if req.family:
        payload["family"] = req.family
    if req.src_ip:
        payload["src_ip"] = req.src_ip

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{AGENT_LAYER_URL}/dispatch/pipeline",
                json={"agent": "triage", "payload": payload, "trace_id": trace_id},
            )
            resp.raise_for_status()
            data = resp.json()

        explain_result = data.get("results", {}).get("explain", {})
        output = explain_result.get("output", {})
        raw_dims = output.get("dimensions", [])

        # 归一化: agent 可能返回 {name, index} 而非 {title, content}
        dims = []
        for d in raw_dims:
            if d.get("title") and d.get("content"):
                dims.append(d)

        # 如果 agent 没返回有效 dimensions，用 fallback 生成
        if len(dims) < 2:
            dims = _fallback_dimensions(req)

        return ExplainResponse(
            domain=req.domain,
            explanation=output.get("explanation", "") or _fallback_explanation(req),
            dimensions=dims,
            confidence=output.get("confidence", 0.0),
            trace_id=trace_id,
        )
    except Exception as e:
        logger.error("explain_dispatch_error", error=str(e))
        return ExplainResponse(
            domain=req.domain,
            explanation=_fallback_explanation(req),
            dimensions=_fallback_dimensions(req),
            trace_id=trace_id,
        )


def _fallback_explanation(req: ExplainRequest) -> str:
    parts = [f"域名 {req.domain}"]
    if req.score is not None:
        parts.append(f"风险评分 {req.score:.2f}")
    if req.family:
        parts.append(f"疑似家族 {req.family}")
    return "基于模型结果：" + "，".join(parts) + "。Agent 调用失败，请检查 Agent Layer 服务状态。"


def _fallback_dimensions(req: ExplainRequest) -> list[dict]:
    """Agent Layer 不可用时，基于请求参数生成四维分析兜底数据。"""
    import math
    from collections import Counter

    domain = req.domain
    sld = domain.split(".")[0]
    length = len(sld)
    digit_ratio = sum(c.isdigit() for c in sld) / max(length, 1)
    vowels = set("aeiou")
    consonant_ratio = sum(c.isalpha() and c.lower() not in vowels for c in sld) / max(length, 1)

    # Shannon entropy
    if sld:
        freq = Counter(sld)
        entropy = -sum((c / length) * math.log2(c / length) for c in freq.values())
    else:
        entropy = 0.0

    score = req.score or 0.0
    family = req.family or "未知"
    src_ip = req.src_ip or "N/A"
    risk = "高" if score >= 0.8 else ("中" if score >= 0.5 else "低")

    return [
        {
            "title": "字符特征分析",
            "content": f"域名 '{domain}' 二级域长度 {length}，数字占比 {digit_ratio:.1%}，辅音占比 {consonant_ratio:.1%}，"
                       f"整体呈现{'机器生成' if digit_ratio > 0.3 or length > 15 else '人工注册'}特征。",
        },
        {
            "title": "熵值分析",
            "content": f"Shannon 熵 {entropy:.2f}，{'高于' if entropy > 3.5 else '接近'}合法域名基线（2.5-3.5），"
                       f"随机性{'较强' if entropy > 3.5 else '一般'}。",
        },
        {
            "title": "DGA家族模式匹配",
            "content": f"疑似家族 {family}，风险评分 {score:.4f}（{risk}风险），"
                       f"建议与 {family} 已知种子/字典做进一步比对。",
        },
        {
            "title": "网络行为关联",
            "content": f"源 IP {src_ip} 发起该域名查询，"
                       f"建议检查该 IP 近期 DNS 请求频率及是否存在批量随机域名查询行为。",
        },
    ]


class ResponseRequest(BaseModel):
    domain: str
    score: float | None = None
    severity: str | None = None
    family: str | None = None
    src_ip: str | None = None


@router.post("/response", dependencies=[Depends(require_analyst)])
async def get_response_actions(req: ResponseRequest):
    """调用 ResponseAgent 获取处置建议"""
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{AGENT_LAYER_URL}/dispatch",
                json={
                    "agent": "response",
                    "payload": {
                        "domain": req.domain,
                        "score": req.score,
                        "severity": req.severity or "MEDIUM",
                        "family": req.family,
                        "src_ip": req.src_ip,
                    },
                },
            )
            resp.raise_for_status()
            data = resp.json()

        # 解包 orchestrator 外层: {"status":"ok","result":{"output":{...}}}
        output = data.get("result", {}).get("output", data)
        actions = output.get("actions", [])

        # 映射 type → level 优先级
        _type_to_level: dict[str, str] = {
            "block_dns": "urgent",
            "isolate_host": "urgent",
            "create_incident": "high",
            "log_event": "medium",
        }

        recommendations = [
            {
                "level": _type_to_level.get(a.get("type", ""), "medium"),
                "action": a.get("description", ""),
            }
            for a in actions
        ]
        return {"recommendations": recommendations}
    except Exception as e:
        logger.error("response_agent_error", error=str(e))
        raise HTTPException(status_code=503, detail="Response agent unavailable")
