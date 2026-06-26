"""
Auto-generated-style protobuf message stubs for scoring.proto
In production, regenerate with: bash compile.sh
"""
from dataclasses import dataclass, field
from typing import List


@dataclass
class Empty:
    pass


@dataclass
class ScoreRequest:
    domain: str = ""
    tenant_id: str = ""
    trace_id: str = ""
    model_version: str = ""


@dataclass
class ScoreResponse:
    domain: str = ""
    score: float = 0.0
    is_dga: bool = False
    family: str = ""
    family_confidence: float = 0.0
    model_version: str = ""
    trace_id: str = ""
    latency_ms: float = 0.0


@dataclass
class BatchScoreRequest:
    domains: List[str] = field(default_factory=list)
    tenant_id: str = ""
    trace_id: str = ""
    model_version: str = ""


@dataclass
class BatchScoreResponse:
    results: List[ScoreResponse] = field(default_factory=list)
    trace_id: str = ""
    total_latency_ms: float = 0.0


@dataclass
class HealthResponse:
    status: str = ""
    model_binary_version: str = ""
    model_multi_version: str = ""
