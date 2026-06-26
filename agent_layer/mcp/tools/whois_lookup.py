"""MCP Tool — WHOIS 查询"""

from __future__ import annotations

import asyncio
import re

from shared.observability import get_logger

logger = get_logger(__name__)


class WhoisLookupTool:
    """Look up WHOIS information for a domain."""

    name = "whois_lookup"
    description = "Look up WHOIS information for a domain"

    input_schema: dict = {
        "type": "object",
        "properties": {
            "domain": {"type": "string"},
        },
        "required": ["domain"],
    }

    async def run(self, **kwargs) -> dict:
        domain: str = kwargs["domain"]
        # 校验域名格式，防止命令注入
        if not re.match(r'^[a-zA-Z0-9][a-zA-Z0-9.-]{0,253}[a-zA-Z0-9]$', domain):
            return {"error": "Invalid domain format"}
        try:
            proc = await asyncio.create_subprocess_exec(
                "whois", domain,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
            raw = stdout.decode(errors="replace")

            if proc.returncode != 0:
                return {"error": f"whois exited with code {proc.returncode}", "stderr": stderr.decode(errors="replace")}

            parsed = self._parse(raw)
            parsed["domain"] = domain
            parsed["raw"] = raw[:4000]  # truncate for safety
            return parsed
        except Exception as exc:
            logger.error("whois_lookup_failed", domain=domain, error=str(exc))
            return {"error": str(exc)}

    @staticmethod
    def _parse(raw: str) -> dict:
        def _find(pattern: str) -> str:
            m = re.search(pattern, raw, re.IGNORECASE)
            return m.group(1).strip() if m else ""

        name_servers: list[str] = re.findall(
            r"Name Server:\s*(.+)", raw, re.IGNORECASE,
        )
        return {
            "registrar": _find(r"Registrar:\s*(.+)"),
            "creation_date": _find(r"Creation Date:\s*(.+)"),
            "expiration_date": _find(r"(?:Expir\w+ Date|Registry Expiry Date):\s*(.+)"),
            "name_servers": [ns.strip().lower() for ns in name_servers],
        }
