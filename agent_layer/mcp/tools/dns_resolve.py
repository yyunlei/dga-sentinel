"""MCP Tool — DNS 解析"""

from __future__ import annotations

import asyncio
import socket
from datetime import datetime, timezone

from shared.observability import get_logger

logger = get_logger(__name__)


class DNSResolveTool:
    """Resolve DNS records for a domain."""

    name = "dns_resolve"
    description = "Resolve DNS records for a domain"

    input_schema: dict = {
        "type": "object",
        "properties": {
            "domain": {"type": "string"},
            "record_type": {
                "type": "string",
                "enum": ["A", "AAAA", "MX", "NS", "TXT", "CNAME"],
                "default": "A",
            },
        },
        "required": ["domain"],
    }

    async def run(self, **kwargs) -> dict:
        domain: str = kwargs["domain"]
        record_type: str = kwargs.get("record_type", "A")
        try:
            records = await self._resolve(domain, record_type)
            return {
                "domain": domain,
                "record_type": record_type,
                "records": records,
                "resolved_at": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as exc:
            logger.error("dns_resolve_failed", domain=domain, error=str(exc))
            return {"error": str(exc)}

    async def _resolve(self, domain: str, record_type: str) -> list[str]:
        # Try dnspython first for full record type support
        try:
            import dns.resolver

            answers = dns.resolver.resolve(domain, record_type)
            return [rdata.to_text() for rdata in answers]
        except ImportError:
            logger.warning("dnspython_not_installed", hint="pip install dnspython for full record type support")

        # Fallback to socket for A/AAAA
        loop = asyncio.get_event_loop()
        family = socket.AF_INET if record_type == "A" else socket.AF_INET6
        if record_type not in ("A", "AAAA"):
            return [f"dnspython not installed; cannot resolve {record_type} records via socket fallback"]

        infos = await loop.getaddrinfo(domain, None, family=family, type=socket.SOCK_STREAM)
        return list({info[4][0] for info in infos})
