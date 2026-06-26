"""
DGA Platform — 可观测性统一初始化
Prometheus 指标 + structlog 结构化日志 + OpenTelemetry 追踪
"""

from __future__ import annotations

import logging
import sys

import structlog
from prometheus_client import Counter, Histogram, Gauge


# ── Prometheus 指标 ───────────────────────────────────

SCORE_REQUESTS = Counter(
    "dga_score_requests_total",
    "Total scoring requests",
    ["endpoint", "tenant_id"],
)

SCORE_LATENCY = Histogram(
    "dga_score_latency_seconds",
    "Scoring latency in seconds",
    ["model_version"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
)

DGA_HITS = Counter(
    "dga_hits_total",
    "Total DGA detections",
    ["family", "severity"],
)

DAG_NODE_LATENCY = Histogram(
    "dga_dag_node_latency_seconds",
    "DAG node processing latency",
    ["pipeline_id", "node_id"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.5),
)

DAG_NODE_ERRORS = Counter(
    "dga_dag_node_errors_total",
    "DAG node processing errors",
    ["pipeline_id", "node_id", "error_type"],
)

ACTIVE_PIPELINES = Gauge(
    "dga_active_pipelines",
    "Number of active DAG pipelines",
)

KAFKA_LAG = Gauge(
    "dga_kafka_consumer_lag",
    "Kafka consumer lag",
    ["topic", "partition"],
)

RATE_LIMIT_REJECTED = Counter(
    "dga_rate_limit_rejected_total",
    "Rate limit rejections",
    ["tenant_id"],
)

AUTH_FAILURES = Counter(
    "dga_auth_failures_total",
    "Authentication failures",
    ["reason"],
)

API_REQUEST_DURATION = Histogram(
    "dga_api_request_duration_seconds",
    "API request duration",
    ["method", "endpoint", "status_code"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5),
)


# ── structlog 配置 ────────────────────────────────────

def setup_logging(log_level: str = "INFO", json_output: bool = True) -> None:
    """初始化 structlog 结构化日志"""
    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if json_output:
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, log_level.upper(), logging.INFO))


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """获取带名称的结构化 logger"""
    return structlog.get_logger(name)


# ── OpenTelemetry 追踪 ────────────────────────────────

def setup_tracing(service_name: str, otlp_endpoint: str = "") -> None:
    """初始化 OpenTelemetry 分布式追踪"""
    if not otlp_endpoint:
        return

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource

        resource = Resource.create({"service.name": service_name})
        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
    except ImportError:
        get_logger(__name__).warning("otel_not_installed", msg="opentelemetry packages not found, tracing disabled")


def get_tracer(name: str):
    """获取 OTel tracer（如果未初始化则返回 NoOp tracer）"""
    try:
        from opentelemetry import trace
        return trace.get_tracer(name)
    except ImportError:
        return None
