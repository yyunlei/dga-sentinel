"""
A2A (Agent-to-Agent) 消息协议
定义 Agent 间通信的消息格式
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from uuid import uuid4


@dataclass
class A2AMessage:
    """Agent 间通信消息"""
    msg_id: str = field(default_factory=lambda: uuid4().hex)
    from_agent: str = ""
    to_agent: str = ""
    action: str = ""          # "query_ioc" | "explain_alert" | "suggest_response" | "correlate"
    payload: dict = field(default_factory=dict)
    trace_id: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    reply_to: str | None = None

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def from_json(cls, data: str | bytes) -> A2AMessage:
        if isinstance(data, bytes):
            data = data.decode()
        d = json.loads(data)
        return cls(**d)

    def reply(self, payload: dict, action: str = "") -> A2AMessage:
        """创建回复消息"""
        return A2AMessage(
            from_agent=self.to_agent,
            to_agent=self.from_agent,
            action=action or f"{self.action}_response",
            payload=payload,
            trace_id=self.trace_id,
            reply_to=self.msg_id,
        )
