"""MCP Tool — GeoIP 查询"""

from __future__ import annotations

import time

from common.observability import get_logger

logger = get_logger(__name__)

# 简单内存缓存 + 速率限制
_geoip_cache: dict[str, tuple[dict, float]] = {}
_CACHE_TTL = 3600  # 1 hour
_rate_calls: list[float] = []
_RATE_LIMIT = 40  # ip-api.com 免费版 45 req/min，留余量


class GeoIPLookupTool:
    """Look up geographic location for an IP address."""

    name = "geoip_lookup"
    description = "Look up geographic location for an IP address"

    input_schema: dict = {
        "type": "object",
        "properties": {
            "ip": {"type": "string"},
        },
        "required": ["ip"],
    }

    async def run(self, **kwargs) -> dict:
        ip: str = kwargs["ip"]
        now = time.time()
        # 缓存命中
        if ip in _geoip_cache:
            cached, ts = _geoip_cache[ip]
            if now - ts < _CACHE_TTL:
                return cached
        # 速率限制
        _rate_calls[:] = [t for t in _rate_calls if now - t < 60]
        if len(_rate_calls) >= _RATE_LIMIT:
            return {"error": "Rate limit exceeded, try again later", "ip": ip}
        try:
            import httpx
            _rate_calls.append(now)
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"http://ip-api.com/json/{ip}")
                resp.raise_for_status()
                data = resp.json()

            if data.get("status") == "fail":
                return {"error": data.get("message", "lookup failed"), "ip": ip}

            result = {
                "ip": ip,
                "country": data.get("country", ""),
                "city": data.get("city", ""),
                "lat": data.get("lat", 0.0),
                "lon": data.get("lon", 0.0),
                "isp": data.get("isp", ""),
                "org": data.get("org", ""),
            }
            _geoip_cache[ip] = (result, time.time())
            return result
        except Exception as exc:
            logger.error("geoip_lookup_failed", ip=ip, error=str(exc))
            return {"error": str(exc)}
