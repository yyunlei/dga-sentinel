"""
DGA Platform — StarRocks Stream Load 公共写入工具
提炼自 business/repositories/starrocks_repo.py，供 dag 等非 business 包调用。
"""

from __future__ import annotations

import base64
import json

import httpx
from common.config import get_settings
from common.observability import get_logger

logger = get_logger(__name__)


def _stream_load_auth(user: str, password: str) -> str:
    """Stream Load 使用 Basic Auth，返回 Header 值"""
    raw = f"{user}:{password}".encode("utf-8")
    return "Basic " + base64.b64encode(raw).decode("ascii")


async def stream_load(events: list[dict], table: str = "dga_events") -> bool:
    """
    通过 StarRocks Stream Load HTTP 写入 dga_analytics.<table>。
    失败记日志返回 False，不抛。
    """
    if not events:
        return True
    settings = get_settings()
    url = (
        f"http://{settings.starrocks_host}:{settings.starrocks_http_port}"
        f"/api/{settings.starrocks_db}/{table}/_stream_load"
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
