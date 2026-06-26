"""StarRocks/PG 表结构 DDL 缓存 + 字段说明"""
from __future__ import annotations
from common.observability import get_logger

logger = get_logger(__name__)

# 允许查询的表白名单及其 DDL + 字段说明
# 字段名 / 类型必须与 deploy/init-scripts/starrocks-tables.sql 真实建表一致，
# 否则 LLM 会生成查询不存在字段的 SQL。
SCHEMA_REGISTRY = {
    "starrocks": {
        "dga_events": {
            "ddl": """CREATE TABLE dga_events (
  event_id VARCHAR(64),
  trace_id VARCHAR(64),
  event_time DATETIME NOT NULL,           -- ⚠ 时间字段名是 event_time（不是 detected_at）
  domain VARCHAR(512) NOT NULL,
  src_ip VARCHAR(64),
  score DOUBLE,                           -- 0..1，越高越可疑
  is_dga BOOLEAN,                         -- TRUE=判定为DGA
  family VARCHAR(64),                     -- DGA 家族名，benign/未知时为 NULL 或空
  family_confidence DOUBLE,
  model_version VARCHAR(32),
  pipeline_id VARCHAR(128),               -- 例如 'dga-realtime-v1'
  tenant_id VARCHAR(64),                  -- 多租户标识，默认 'default'
  severity VARCHAR(16)                    -- 'CRITICAL' / 'HIGH' / 'MEDIUM' / 'LOW'
)
PARTITION BY RANGE(event_time) (...)      -- 按天分区
DISTRIBUTED BY HASH(domain) BUCKETS 4""",
            "description": "DGA 检测事件表，所有评分结果都写入此表（包括正常和 DGA）",
            "fields": {
                "event_id": "事件唯一ID（UUID）",
                "trace_id": "分布式追踪ID",
                "event_time": "事件时间（DATETIME，按天分区）",
                "domain": "被检测的域名",
                "src_ip": "发起DNS查询的源IP",
                "score": "DGA风险评分 0..1",
                "is_dga": "是否判定为DGA（true/false）",
                "family": "疑似DGA家族（如 verblecon/qakbot；正常域名为 NULL）",
                "severity": "严重度（按 score 阈值映射）：CRITICAL (≥0.95) / HIGH (≥0.85) / MEDIUM (≥0.5) / LOW (<0.5)。用户说『高危/高风险』通常指 severity IN ('CRITICAL','HIGH')，不是仅 'HIGH'",
                "pipeline_id": "DAG pipeline 标识",
                "tenant_id": "租户ID（默认 default）",
            },
            "examples": [
                "-- 今日高危告警（CRITICAL + HIGH 严重度）\nSELECT COUNT(*) FROM dga_events WHERE event_time >= CURDATE() AND severity IN ('CRITICAL','HIGH');",
                "-- 今日 DGA 告警总数\nSELECT COUNT(*) FROM dga_events WHERE event_time >= CURDATE() AND is_dga = TRUE;",
                "-- 最近 7 天每天的 DGA 数量\nSELECT DATE(event_time) AS day, COUNT(*) AS dga_cnt FROM dga_events WHERE is_dga=TRUE AND event_time >= DATE_SUB(CURDATE(), INTERVAL 7 DAY) GROUP BY day ORDER BY day;",
                "-- DGA 家族 Top 10\nSELECT family, COUNT(*) AS cnt FROM dga_events WHERE is_dga=TRUE AND family IS NOT NULL AND family<>'' GROUP BY family ORDER BY cnt DESC LIMIT 10;",
                "-- 严重度分布\nSELECT severity, COUNT(*) AS cnt FROM dga_events GROUP BY severity ORDER BY cnt DESC;",
                "-- 每小时检测量趋势（最近 24h）\nSELECT DATE_FORMAT(event_time,'%Y-%m-%d %H:00') AS hour, COUNT(*) AS cnt FROM dga_events WHERE event_time >= DATE_SUB(NOW(), INTERVAL 24 HOUR) GROUP BY hour ORDER BY hour;",
                "-- 高分域名 Top 20\nSELECT domain, MAX(score) AS max_score, COUNT(*) AS hits FROM dga_events WHERE is_dga=TRUE GROUP BY domain ORDER BY max_score DESC LIMIT 20;",
            ],
        },
    },
    "postgres": {
        "model_versions": {
            "ddl": """CREATE TABLE model_versions (
  id SERIAL PRIMARY KEY,
  model_id VARCHAR(64) NOT NULL,
  version VARCHAR(32) NOT NULL,
  artifact_path TEXT NOT NULL,
  metrics JSONB DEFAULT '{}',
  status VARCHAR(16) DEFAULT 'staging',
  ab_weight REAL DEFAULT 0.0,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  deployed_at TIMESTAMPTZ,
  UNIQUE(model_id, version)
)""",
            "description": "模型版本管理表",
            "fields": {
                "model_id": "模型标识",
                "version": "版本号",
                "artifact_path": "模型制品路径",
                "status": "状态 (production/staging/archived)",
                "ab_weight": "A/B 权重",
                "created_at": "创建时间",
                "deployed_at": "部署时间",
            },
        },
        "feedback": {
            "ddl": """CREATE TABLE feedback (
  id SERIAL PRIMARY KEY,
  event_id VARCHAR(64),
  domain VARCHAR(253),
  true_label VARCHAR(32),
  predicted_label VARCHAR(32),
  score REAL,
  annotator VARCHAR(64),
  created_at TIMESTAMPTZ DEFAULT NOW()
)""",
            "description": "分析师反馈表",
            "fields": {
                "event_id": "关联事件ID",
                "domain": "域名",
                "true_label": "真实标签 (dga/benign)",
                "predicted_label": "模型预测标签",
                "score": "模型评分",
                "annotator": "标注人",
                "created_at": "提交时间",
            },
        },
    },
}


def get_schema_context(db_type: str = "starrocks") -> str:
    """生成供 LLM 使用的表结构上下文（含示例查询）"""
    schemas = SCHEMA_REGISTRY.get(db_type, {})
    parts = []
    for table_name, info in schemas.items():
        parts.append(f"-- 表: {table_name} ({info['description']})")
        parts.append(info["ddl"])
        examples = info.get("examples") or []
        if examples:
            parts.append("\n-- 示例查询（可直接借鉴语法）：")
            for ex in examples:
                parts.append(ex)
        parts.append("")
    return "\n".join(parts)


def get_allowed_tables(db_type: str = "starrocks") -> set[str]:
    return set(SCHEMA_REGISTRY.get(db_type, {}).keys())