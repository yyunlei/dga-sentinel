"""
Agent 监控 HTTP 客户端 — 封装对 agent-layer 服务的 httpx 调用。
业务逻辑（响应组装、参数编排）不在此处。
"""
from __future__ import annotations

import httpx


class AgentMonitorClient:
    """对 agent-layer 服务的 HTTP 代理：fetch_metrics / fetch_exec_history / fetch_a2a_messages。

    构造时注入 base_url，方便单测替换。
    """

    def __init__(self, base_url: str, timeout: float = 5.0) -> None:
        """
        :param base_url: agent-layer 服务根地址，如 http://agent-layer:8002
        :param timeout:  httpx 超时秒数（与原路由保持一致，默认 5.0）
        """
        self._base_url = base_url
        self._timeout = timeout

    async def fetch_metrics(self) -> dict:
        """GET {base_url}/agents — 返回原始 JSON。

        HTTP 错误或网络异常原样向上抛出，由 api 层负责映射为 HTTPException(503)。
        """
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(f"{self._base_url}/agents")
            resp.raise_for_status()
            return resp.json()

    async def fetch_exec_history(self, limit: int) -> dict:
        """GET {base_url}/agents/exec-history — 返回执行历史 JSON。

        404 → {"records": []}；其他任何异常 → {"records": []}。
        与原路由静默降级行为保持一致。
        """
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(
                    f"{self._base_url}/agents/exec-history",
                    params={"limit": limit},
                )
                if resp.status_code == 404:
                    return {"records": []}
                resp.raise_for_status()
                return resp.json()
        except Exception:
            return {"records": []}

    async def fetch_a2a_messages(self, limit: int) -> dict:
        """GET {base_url}/agents/a2a-messages — 返回 A2A 消息流 JSON。

        404 → {"messages": []}；其他任何异常 → {"messages": []}。
        与原路由静默降级行为保持一致。
        """
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(
                    f"{self._base_url}/agents/a2a-messages",
                    params={"limit": limit},
                )
                if resp.status_code == 404:
                    return {"messages": []}
                resp.raise_for_status()
                return resp.json()
        except Exception:
            return {"messages": []}
