"""
Gateway — StarRocks Stream Load 写入
域名检测完成后将命中结果写入 StarRocks 分析表 dga_analytics.dga_events
"""

from __future__ import annotations

import base64
import json
from typing import Any

import httpx
from shared.config import get_settings
from shared.observability import get_logger

logger = get_logger(__name__)

# 表 dga_events 字段（与 deploy/init-scripts/starrocks-tables.sql 一致）
TABLE_DGA_EVENTS = "dga_events"


def _stream_load_auth(user: str, password: str) -> str:
    """Stream Load 使用 Basic Auth，返回 Header 值"""
    raw = f"{user}:{password}".encode("utf-8")
    return "Basic " + base64.b64encode(raw).decode("ascii")


async def write_events_to_starrocks(events: list[dict[str, Any]]) -> bool:
    """
    通过 Stream Load HTTP 接口将事件写入 StarRocks dga_analytics.dga_events。
    单条或批量均可；失败时打日志并返回 False，不抛异常。
    """
    if not events:
        return True
    settings = get_settings()
    url = (
        f"http://{settings.starrocks_host}:{settings.starrocks_http_port}"
        f"/api/{settings.starrocks_db}/{TABLE_DGA_EVENTS}/_stream_load"
    )
    auth = _stream_load_auth(settings.starrocks_user, settings.starrocks_password)
    # 使用 JSON 数组 + strip_outer_array: true 写入多行
    body = json.dumps(events, ensure_ascii=False)
    headers = {
        "Authorization": auth,
        "Content-Type": "application/json",
        "Expect": "100-continue",
        "format": "json",
        "strip_outer_array": "true",
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.put(url, content=body.encode("utf-8"), headers=headers)
            # FE 307 重定向到 BE，需要手动跟随并保留 auth header
            if resp.status_code == 307:
                redirect_url = resp.headers.get("location", "")
                if redirect_url:
                    resp = await client.put(
                        redirect_url, content=body.encode("utf-8"), headers=headers,
                    )
            if resp.status_code != 200:
                logger.warning(
                    "starrocks_stream_load_failed",
                    status=resp.status_code,
                    body=resp.text[:500],
                )
                return False
            data = resp.json()
            if data.get("Status") != "Success":
                logger.warning(
                    "starrocks_stream_load_status",
                    status=data.get("Status"),
                    message=data.get("Message", ""),
                )
                return False
            logger.info("starrocks_stream_load_ok", rows=len(events))
            return True
    except Exception as e:
        logger.warning("starrocks_stream_load_error", error=str(e))
        return False
