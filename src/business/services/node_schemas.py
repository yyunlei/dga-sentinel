"""
节点配置 Schema 常量 — 19 种 DAG 节点类型的预定义 schema。
内容原样保留，键名和值字节级不变（包括 "scoring_service" 等标识符）。
"""
from __future__ import annotations

NODE_CONFIG_SCHEMAS: dict[str, dict] = {
    "kafka_consumer": {
        "category": "ingest",
        "fields": [
            {"key": "topic", "type": "string", "label": "Kafka Topic", "required": True, "default": "dns-query-logs"},
            {"key": "group_id", "type": "string", "label": "Consumer Group", "required": True, "default": "dga-detector-v1"},
            {"key": "bootstrap_servers", "type": "string", "label": "Bootstrap Servers", "default": "kafka:9092"},
            {"key": "auto_offset_reset", "type": "enum", "label": "Offset Reset", "options": ["earliest", "latest"], "default": "earliest"},
        ],
    },
    "file_reader": {
        "category": "ingest",
        "fields": [
            {"key": "directory", "type": "string", "label": "目录路径", "required": True, "default": "/data/dns-logs"},
            {"key": "pattern", "type": "string", "label": "文件匹配模式", "default": "*.csv"},
            {"key": "batch_size", "type": "number", "label": "批次大小", "default": 1000},
        ],
    },
    "dns_parser": {
        "category": "transform",
        "fields": [
            {"key": "fields", "type": "array", "label": "解析字段", "default": ["query_name", "query_type", "src_ip", "timestamp"]},
        ],
    },
    "feature_extractor": {
        "category": "transform",
        "fields": [
            {"key": "extractors", "type": "array", "label": "特征提取器", "default": ["lexical", "entropy", "ngram"]},
        ],
    },
    "scoring_service": {
        "category": "infer",
        "fields": [
            {"key": "endpoint", "type": "string", "label": "服务地址", "required": True, "default": "scoring-service:50051"},
            {"key": "timeout_ms", "type": "number", "label": "超时(ms)", "default": 100},
            {"key": "model_version", "type": "string", "label": "模型版本", "default": "latest"},
        ],
    },
    "whitelist": {
        "category": "filter",
        "fields": [
            {"key": "source", "type": "string", "label": "白名单来源", "default": "redis"},
            {"key": "key", "type": "string", "label": "Redis Key", "default": "whitelist:domains"},
            {"key": "ttl", "type": "number", "label": "缓存TTL(秒)", "default": 3600},
        ],
    },
    "threshold": {
        "category": "filter",
        "fields": [
            {"key": "min_score", "type": "number", "label": "最低分数", "default": 0.5},
            {"key": "max_score", "type": "number", "label": "最高分数", "default": 1.0},
        ],
    },
    "blacklist": {
        "category": "filter",
        "fields": [
            {"key": "source", "type": "string", "label": "黑名单来源", "default": "redis"},
            {"key": "key", "type": "string", "label": "Redis Key", "default": "blacklist:domains"},
        ],
    },
    "es_sink": {
        "category": "sink",
        "fields": [
            {"key": "index_prefix", "type": "string", "label": "索引前缀", "required": True, "default": "dga-events"},
            {"key": "hosts", "type": "string", "label": "ES 地址", "default": "http://elasticsearch:9200"},
        ],
    },
    "kafka_sink": {
        "category": "sink",
        "fields": [
            {"key": "topic", "type": "string", "label": "输出 Topic", "required": True, "default": "dga-alerts"},
            {"key": "bootstrap_servers", "type": "string", "label": "Bootstrap Servers", "default": "kafka:9092"},
        ],
    },
    "starrocks_sink": {
        "category": "sink",
        "fields": [
            {"key": "database", "type": "string", "label": "数据库", "default": "dga_analytics"},
            {"key": "table", "type": "string", "label": "表名", "default": "dga_events"},
            {"key": "hosts", "type": "string", "label": "FE 地址", "default": "starrocks:8030"},
        ],
    },
    "fan_out": {
        "category": "sink",
        "fields": [
            {"key": "targets", "type": "array", "label": "输出目标", "default": []},
        ],
    },
    "multi_sink": {
        "category": "sink",
        "fields": [
            {"key": "routes", "type": "array", "label": "路由规则", "default": []},
            {"key": "default_target", "type": "enum", "label": "默认输出", "options": ["es", "kafka", "starrocks", "drop"], "default": "es"},
            {"key": "es_index", "type": "string", "label": "ES 索引", "default": "dga-events"},
            {"key": "kafka_topic", "type": "string", "label": "Kafka Topic", "default": "dga-alerts"},
            {"key": "starrocks_table", "type": "string", "label": "StarRocks 表", "default": "dga_events"},
        ],
    },
    "es_source": {
        "category": "ingest",
        "fields": [
            {"key": "hosts", "type": "string", "label": "ES 集群地址", "required": True, "default": "http://elasticsearch:9200"},
            {"key": "index", "type": "string", "label": "索引模式", "required": True, "default": "dns-logs-*"},
            {"key": "query", "type": "string", "label": "查询 DSL (JSON)"},
            {"key": "scroll_size", "type": "number", "label": "每次滚动条数", "default": 1000},
            {"key": "scroll_timeout", "type": "string", "label": "滚动超时", "default": "5m"},
            {"key": "fields", "type": "array", "label": "返回字段", "default": ["domain", "src_ip", "timestamp"]},
        ],
    },
    "severity_tag": {
        "category": "transform",
        "fields": [
            {"key": "critical_threshold", "type": "number", "label": "CRITICAL 阈值 (>=)", "default": 0.95},
            {"key": "high_threshold", "type": "number", "label": "HIGH 阈值 (>=)", "default": 0.85},
            {"key": "medium_threshold", "type": "number", "label": "MEDIUM 阈值 (>=)", "default": 0.7},
            {"key": "score_field", "type": "string", "label": "分数字段", "default": "score"},
            {"key": "output_field", "type": "string", "label": "输出字段", "default": "severity"},
        ],
    },
    "threat_intel_enrich": {
        "category": "transform",
        "fields": [
            {"key": "providers", "type": "array", "label": "情报源", "required": True, "default": ["virustotal"]},
            {"key": "api_key_env", "type": "string", "label": "API Key 环境变量"},
            {"key": "cache_ttl", "type": "number", "label": "缓存 TTL (秒)", "default": 3600},
            {"key": "timeout_ms", "type": "number", "label": "查询超时 (ms)", "default": 5000},
            {"key": "enrich_fields", "type": "array", "label": "富化字段", "default": ["reputation", "malware_family"]},
            {"key": "fail_open", "type": "boolean", "label": "查询失败时放行", "default": True},
        ],
    },
    "geoip_lookup": {
        "category": "transform",
        "fields": [
            {"key": "ip_field", "type": "string", "label": "IP 字段", "required": True, "default": "src_ip"},
            {"key": "database", "type": "enum", "label": "GeoIP 数据库", "options": ["maxmind", "ip2location", "dbip"], "default": "maxmind"},
            {"key": "db_path", "type": "string", "label": "数据库文件路径"},
            {"key": "output_fields", "type": "array", "label": "输出字段", "default": ["country", "city", "asn"]},
            {"key": "high_risk_countries", "type": "array", "label": "高风险国家代码", "default": []},
        ],
    },
    "risk_aggregate": {
        "category": "transform",
        "fields": [
            {"key": "dga_score_weight", "type": "number", "label": "DGA 评分权重", "default": 0.4},
            {"key": "threat_intel_weight", "type": "number", "label": "威胁情报权重", "default": 0.3},
            {"key": "geoip_risk_weight", "type": "number", "label": "地理风险权重", "default": 0.3},
            {"key": "aggregation_method", "type": "enum", "label": "聚合方法", "options": ["weighted_sum", "max", "bayesian"], "default": "weighted_sum"},
            {"key": "output_field", "type": "string", "label": "输出字段", "default": "risk_score"},
        ],
    },
    "family_classify": {
        "category": "infer",
        "fields": [
            {"key": "endpoint", "type": "string", "label": "服务地址", "required": True, "default": "http://scoring-service:8000"},
            {"key": "model_id", "type": "string", "label": "模型 ID", "default": "multi-cnn-attention"},
            {"key": "top_k", "type": "number", "label": "返回 Top-K 家族", "default": 3},
            {"key": "min_confidence", "type": "number", "label": "最低置信度", "default": 0.3},
            {"key": "timeout_ms", "type": "number", "label": "推理超时 (ms)", "default": 300},
            {"key": "only_dga", "type": "boolean", "label": "仅对 DGA 域名分类", "default": True},
        ],
    },
}
