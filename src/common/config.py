"""
DGA Platform — 统一配置管理
使用 pydantic-settings 从环境变量 / .env 加载配置
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _find_project_root(start: Path) -> Path:
    """向上查找含 pyproject.toml 的目录作为项目根(容器内 /app,host 为仓库根)。"""
    for candidate in (start, *start.parents):
        if (candidate / "pyproject.toml").exists():
            return candidate
    return start.parents[1]  # 兜底:旧行为

_PROJECT_ROOT = _find_project_root(Path(__file__).resolve())
PROJECT_ROOT = _PROJECT_ROOT  # 公共别名,供其它模块统一引用


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- 通用 ---
    app_env: str = "development"
    log_level: str = "INFO"
    trace_enabled: bool = True
    otel_endpoint: str = ""  # e.g. http://jaeger:4317

    # --- API 网关 ---
    gateway_host: str = "0.0.0.0"
    gateway_port: int = 8000
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    rate_limit_per_minute: int = 600

    # --- 评分服务 ---
    scoring_host: str = "localhost"
    scoring_http_port: int = 8001
    scoring_grpc_port: int = 50051
    model_binary_path: str = "artifacts/binary/binary_classification_model.pkl"
    model_multi_path: str = "artifacts/multi/multiclass_classification_model.h5"

    # --- DAG 引擎 ---
    dag_pipeline_dir: str = "src/dag/pipelines"

    # --- Kafka ---
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_dns_topic: str = "dns-query-logs"
    kafka_alert_topic: str = "dga-alerts"

    # --- Elasticsearch ---
    es_hosts: str = "http://localhost:9200"
    es_index_prefix: str = "dga-events"

    # --- StarRocks ---
    starrocks_host: str = "localhost"
    starrocks_port: int = 9030
    starrocks_http_port: int = 8030
    starrocks_db: str = "dga_analytics"
    starrocks_user: str = "root"
    starrocks_password: str = ""

    # --- Redis ---
    redis_url: str = "redis://localhost:6379/0"

    # --- PostgreSQL ---
    pg_dsn: str = "postgresql://dga:dga_password@localhost:5432/dga_platform"

    # --- DeepSeek LLM ---
    # 必须通过环境变量 DEEPSEEK_API_KEY 配置有效 key，否则解释接口返回「未配置」提示
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"

    # --- Prometheus ---
    prometheus_port: int = 9090

    # --- Grafana ---
    grafana_port: int = 3001
    grafana_admin_password: str = "admin"

    @property
    def is_dev(self) -> bool:
        return self.app_env == "development"

    @model_validator(mode="after")
    def _check_secrets(self) -> "Settings":
        if not self.is_dev:
            if self.jwt_secret == "change-me-in-production":
                raise ValueError("JWT_SECRET must be changed in non-dev environments")
            if self.grafana_admin_password == "admin":
                raise ValueError("GRAFANA_ADMIN_PASSWORD must be changed in non-dev environments")
        return self

    @property
    def starrocks_uri(self) -> str:
        return f"mysql://{self.starrocks_user}:{self.starrocks_password}@{self.starrocks_host}:{self.starrocks_port}/{self.starrocks_db}"


@lru_cache
def get_settings() -> Settings:
    return Settings()


_PLACEHOLDER_API_KEYS = frozenset({
    "", "your-deepseek-api-key", "sk-xxx", "change-me",
})


def has_valid_llm_key() -> bool:
    """检测 DeepSeek API key 是否为有效值（非空且非占位符）。"""
    key = (get_settings().deepseek_api_key or "").strip().lower()
    return key not in _PLACEHOLDER_API_KEYS
