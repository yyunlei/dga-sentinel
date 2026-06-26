-- DGA Platform — PostgreSQL 初始化脚本

-- 模型注册表
CREATE TABLE IF NOT EXISTS model_versions (
    id              SERIAL PRIMARY KEY,
    model_id        VARCHAR(64) NOT NULL,       -- "binary-xgboost" / "multi-cnn-attention"
    version         VARCHAR(32) NOT NULL,
    artifact_path   TEXT NOT NULL,
    metrics         JSONB DEFAULT '{}',          -- {accuracy, f1, precision, recall, auc}
    status          VARCHAR(16) DEFAULT 'staging', -- staging / production / archived
    ab_weight       REAL DEFAULT 0.0,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    deployed_at     TIMESTAMPTZ,
    UNIQUE(model_id, version)
);

-- Pipeline 配置
CREATE TABLE IF NOT EXISTS pipeline_configs (
    id              SERIAL PRIMARY KEY,
    pipeline_id     VARCHAR(128) UNIQUE NOT NULL,
    name            VARCHAR(256) NOT NULL,
    mode            VARCHAR(16) NOT NULL,        -- stream / batch
    yaml_content    TEXT NOT NULL,
    status          VARCHAR(16) DEFAULT 'stopped',
    version         VARCHAR(32) DEFAULT '1.0.0',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- 租户配置
CREATE TABLE IF NOT EXISTS tenant_configs (
    id                  SERIAL PRIMARY KEY,
    tenant_id           VARCHAR(64) UNIQUE NOT NULL,
    name                VARCHAR(256) NOT NULL,
    threshold_overrides JSONB DEFAULT '{}',
    whitelist_key       VARCHAR(128) DEFAULT '',
    rate_limit          INT DEFAULT 600,
    api_key_hash        VARCHAR(256) DEFAULT '',
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

-- 插入默认租户
INSERT INTO tenant_configs (tenant_id, name, rate_limit)
VALUES ('default', 'Default Tenant', 600)
ON CONFLICT (tenant_id) DO NOTHING;

-- 插入现有模型版本
INSERT INTO model_versions (model_id, version, artifact_path, status, ab_weight)
VALUES
    ('binary-xgboost', 'v1.0.0', 'artifacts/binary/binary_classification_model.pkl', 'production', 1.0),
    ('multi-cnn-attention', 'v1.0.0', 'artifacts/multi/multiclass_classification_model.h5', 'production', 1.0)
ON CONFLICT (model_id, version) DO NOTHING;

-- 反馈标注表
CREATE TABLE IF NOT EXISTS feedback (
    id              SERIAL PRIMARY KEY,
    event_id        VARCHAR(64),
    domain          VARCHAR(253),
    true_label      VARCHAR(32),
    predicted_label VARCHAR(32),
    score           REAL,
    family          VARCHAR(64),
    annotator       VARCHAR(64),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_feedback_family ON feedback(family);
CREATE INDEX IF NOT EXISTS idx_feedback_created_family ON feedback(created_at, family);

-- 审计日志表
CREATE TABLE IF NOT EXISTS audit_log (
    id              SERIAL PRIMARY KEY,
    user_id         VARCHAR(64),
    action          VARCHAR(64) NOT NULL,
    resource        VARCHAR(256),
    detail          JSONB DEFAULT '{}',
    ip_address      VARCHAR(45),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_log_user ON audit_log(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_created ON audit_log(created_at);

-- 节点配置表
CREATE TABLE IF NOT EXISTS node_configs (
    id              SERIAL PRIMARY KEY,
    node_type       VARCHAR(32) NOT NULL,
    category        VARCHAR(16) NOT NULL,
    name            VARCHAR(128) NOT NULL,
    config          JSONB NOT NULL DEFAULT '{}',
    description     TEXT DEFAULT '',
    created_by      VARCHAR(64) DEFAULT 'system',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(node_type, name)
);

CREATE INDEX IF NOT EXISTS idx_node_configs_type ON node_configs(node_type);
CREATE INDEX IF NOT EXISTS idx_node_configs_category ON node_configs(category);

-- Pipeline 操作历史表
CREATE TABLE IF NOT EXISTS pipeline_operations (
    id              SERIAL PRIMARY KEY,
    pipeline_id     VARCHAR(128) NOT NULL,
    operation       VARCHAR(32) NOT NULL,
    operator        VARCHAR(64) DEFAULT 'system',
    status          VARCHAR(16) DEFAULT 'success',
    detail          JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pipeline_ops_pipeline ON pipeline_operations(pipeline_id);
CREATE INDEX IF NOT EXISTS idx_pipeline_ops_created ON pipeline_operations(created_at);

-- Pipeline 节点表（结构化存储每个 DAG 节点）
CREATE TABLE IF NOT EXISTS pipeline_nodes (
    id              SERIAL PRIMARY KEY,
    pipeline_id     VARCHAR(128) NOT NULL REFERENCES pipeline_configs(pipeline_id) ON DELETE CASCADE,
    node_id         VARCHAR(128) NOT NULL,
    node_type       VARCHAR(64) NOT NULL,
    sub_type        VARCHAR(64) NOT NULL,
    label           VARCHAR(256) DEFAULT '',
    config          JSONB NOT NULL DEFAULT '{}',
    position_x      REAL DEFAULT 0,
    position_y      REAL DEFAULT 0,
    sort_order      INT DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(pipeline_id, node_id)
);

CREATE INDEX IF NOT EXISTS idx_pipeline_nodes_pipeline ON pipeline_nodes(pipeline_id);

-- Pipeline 边表（结构化存储节点连接关系）
CREATE TABLE IF NOT EXISTS pipeline_edges (
    id              SERIAL PRIMARY KEY,
    pipeline_id     VARCHAR(128) NOT NULL REFERENCES pipeline_configs(pipeline_id) ON DELETE CASCADE,
    source_node_id  VARCHAR(128) NOT NULL,
    target_node_id  VARCHAR(128) NOT NULL,
    edge_type       VARCHAR(32) DEFAULT 'default',
    condition       VARCHAR(256) DEFAULT '',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(pipeline_id, source_node_id, target_node_id)
);

CREATE INDEX IF NOT EXISTS idx_pipeline_edges_pipeline ON pipeline_edges(pipeline_id);

-- ══════════════════════════════════════════════════════════════════
--  种子数据 — Pipeline 配置
-- ══════════════════════════════════════════════════════════════════

INSERT INTO pipeline_configs (pipeline_id, name, mode, yaml_content, status, version, created_at, updated_at)
VALUES
(
  'dga-realtime-v1',
  'DGA 实时检测流水线',
  'stream',
  E'pipeline:\n  name: dga-realtime-v1\n  mode: stream\n  version: "1.0.0"\n\nnodes:\n  - id: ingest\n    type: kafka_consumer\n    config:\n      topic: dns-query-logs\n      group_id: dga-detector-v1\n      auto_offset_reset: latest\n\n  - id: parse\n    type: dns_parser\n    config:\n      fields: [query_name, query_type, src_ip, timestamp]\n\n  - id: feature\n    type: feature_extractor\n    config:\n      extractors:\n        - lexical\n        - entropy\n\n  - id: infer\n    type: scoring_service\n    config:\n      endpoint: "http://scoring-service:8000"\n      protocol: http\n      timeout_ms: 500\n\n  - id: whitelist\n    type: whitelist\n    config:\n      source: static\n      static:\n        - google.com\n        - microsoft.com\n        - apple.com\n\n  - id: threshold\n    type: threshold\n    config:\n      default: 0.7\n\n  - id: sink\n    type: multi_sink\n    config:\n      targets:\n        - type: kafka\n          topic: dga-alerts\n          condition: "score >= threshold"\n        - type: es\n          index: dga-events-{date}\n          condition: always',
  'running',
  '3',
  NOW() - INTERVAL '7 days',
  NOW() - INTERVAL '1 day'
),
-- __CONTINUE_SEED_2__
(
  'dga-batch-v1',
  'DGA 批量回溯分析',
  'batch',
  E'pipeline:\n  name: dga-batch-v1\n  mode: batch\n  version: "1.0.0"\n\nnodes:\n  - id: ingest\n    type: file_reader\n    config:\n      path: ""\n\n  - id: parse\n    type: dns_parser\n    config:\n      fields: [query_name, query_type, src_ip, timestamp]\n\n  - id: feature\n    type: feature_extractor\n    config:\n      extractors:\n        - lexical\n        - entropy\n\n  - id: infer\n    type: scoring_service\n    config:\n      endpoint: "http://scoring-service:8000"\n      protocol: http\n      timeout_ms: 1000\n\n  - id: threshold\n    type: threshold\n    config:\n      default: 0.7\n\n  - id: sink\n    type: multi_sink\n    config:\n      targets:\n        - type: es\n          index: dga-events-{date}\n          condition: always\n        - type: starrocks\n          table: dga_events\n          condition: always',
  'stopped',
  '2',
  NOW() - INTERVAL '5 days',
  NOW() - INTERVAL '2 days'
),
-- __CONTINUE_SEED_3__
(
  'c2-realtime-v1',
  'C2 域名实时检测',
  'stream',
  E'pipeline:\n  name: c2-realtime-v1\n  mode: stream\n  version: "1.0.0"\n\nnodes:\n  - id: ingest\n    type: kafka_consumer\n    config:\n      topic: dns-query-logs\n      group_id: c2-detector-v1\n      auto_offset_reset: latest\n\n  - id: parse\n    type: dns_parser\n    config:\n      fields: [query_name, query_type, src_ip, timestamp]\n\n  - id: feature\n    type: feature_extractor\n    config:\n      extractors:\n        - entropy\n        - lexical\n\n  - id: infer\n    type: scoring_service\n    config:\n      endpoint: "http://scoring-service:8000"\n      protocol: http\n      timeout_ms: 100\n\n  - id: whitelist\n    type: whitelist\n    config:\n      source: redis\n\n  - id: threshold\n    type: threshold\n    config:\n      default: 0.6\n\n  - id: sink\n    type: multi_sink\n    config:\n      targets:\n        - type: kafka\n          topic: c2-alerts\n          condition: "score >= threshold"\n        - type: es\n          index: c2-events-{date}\n          condition: always',
  'running',
  '1',
  NOW() - INTERVAL '3 days',
  NOW() - INTERVAL '3 days'
),
(
  'dns-tunnel-v1',
  'DNS 隧道检测',
  'stream',
  E'pipeline:\n  name: dns-tunnel-v1\n  mode: stream\n  version: "1.0.0"\n\nnodes:\n  - id: ingest\n    type: kafka_consumer\n    config:\n      topic: dns-query-logs\n      group_id: dns-tunnel-detector-v1\n      auto_offset_reset: latest\n\n  - id: parse\n    type: dns_parser\n    config:\n      fields: [query_name, query_type, src_ip, timestamp, response_size]\n\n  - id: feature\n    type: feature_extractor\n    config:\n      extractors:\n        - entropy\n        - lexical\n        - ngram\n\n  - id: infer\n    type: scoring_service\n    config:\n      endpoint: "http://scoring-service:8000"\n      protocol: http\n      timeout_ms: 100\n\n  - id: whitelist\n    type: whitelist\n    config:\n      source: redis\n\n  - id: threshold\n    type: threshold\n    config:\n      default: 0.65\n\n  - id: sink\n    type: multi_sink\n    config:\n      targets:\n        - type: kafka\n          topic: dns-tunnel-alerts\n          condition: "score >= threshold"\n        - type: es\n          index: dns-tunnel-events-{date}\n          condition: always',
  'stopped',
  '1',
  NOW() - INTERVAL '2 days',
  NOW() - INTERVAL '2 days'
)
ON CONFLICT (pipeline_id) DO NOTHING;

-- ══════════════════════════════════════════════════════════════════
--  种子数据 — Pipeline 操作历史
-- ══════════════════════════════════════════════════════════════════

INSERT INTO pipeline_operations (pipeline_id, operation, operator, status, detail, created_at) VALUES
('dga-realtime-v1', 'create',  'admin', 'success', '{"version": 1}',                          NOW() - INTERVAL '7 days'),
('dga-realtime-v1', 'save',    'admin', 'success', '{"version": 2}',                          NOW() - INTERVAL '4 days'),
('dga-realtime-v1', 'save',    'admin', 'success', '{"version": 3}',                          NOW() - INTERVAL '1 day'),
('dga-realtime-v1', 'start',   'admin', 'success', '{}',                                      NOW() - INTERVAL '1 day'),
('dga-batch-v1',    'create',  'admin', 'success', '{"version": 1}',                          NOW() - INTERVAL '5 days'),
('dga-batch-v1',    'save',    'admin', 'success', '{"version": 2}',                          NOW() - INTERVAL '2 days'),
('dga-batch-v1',    'replay',  'admin', 'success', '{"replay_id":"r-001","date":"2026-02-10"}', NOW() - INTERVAL '2 days'),
('dga-batch-v1',    'stop',    'admin', 'success', '{}',                                      NOW() - INTERVAL '2 days'),
('c2-realtime-v1',  'create',  'admin', 'success', '{"version": 1}',                          NOW() - INTERVAL '3 days'),
('c2-realtime-v1',  'start',   'admin', 'success', '{}',                                      NOW() - INTERVAL '3 days'),
('dns-tunnel-v1',   'create',  'admin', 'success', '{"version": 1}',                          NOW() - INTERVAL '2 days'),
('dns-tunnel-v1',   'start',   'admin', 'success', '{}',                                      NOW() - INTERVAL '2 days'),
('dns-tunnel-v1',   'stop',    'admin', 'success', '{}',                                      NOW() - INTERVAL '1 day');

-- ══════════════════════════════════════════════════════════════════
--  种子数据 — 预置节点配置模板
-- ══════════════════════════════════════════════════════════════════

INSERT INTO node_configs (node_type, category, name, config, description) VALUES
(
  'kafka_consumer', 'ingest', 'DNS 日志默认消费者',
  '{"topic":"dns-query-logs","group_id":"dga-detector-v1","bootstrap_servers":"kafka:9092","auto_offset_reset":"latest","max_poll_records":500}',
  '标准 DNS 日志 Kafka 消费配置，适用于实时检测场景'
),
(
  'scoring_service', 'infer', 'DGA 二分类评分 (生产)',
  '{"endpoint":"http://scoring-service:8000","model_id":"binary-xgboost","threshold":0.7,"timeout_ms":200,"batch_size":32,"protocol":"http","cache_enabled":true,"cache_ttl":300}',
  '生产环境 DGA 二分类模型评分配置'
),
(
  'es_sink', 'sink', 'DGA 事件 ES 输出',
  '{"hosts":"http://elasticsearch:9200","index":"dga-events","index_date_pattern":"daily","condition":"always","bulk_size":200,"flush_interval_ms":5000}',
  '将所有检测事件写入 Elasticsearch 按天索引'
),
(
  'threshold', 'filter', '标准阈值过滤 (0.7)',
  '{"min_score":0.7,"score_field":"score","severity_rules":"auto","critical_threshold":0.95,"high_threshold":0.85,"action_below":"drop"}',
  '标准 DGA 检测阈值配置，0.7 以上判定为 DGA'
),
(
  'whitelist', 'filter', '常用白名单配置',
  '{"source":"redis","redis_key":"whitelist:domains","redis_url":"redis://redis:6379","match_mode":"suffix","refresh_interval":300,"on_match":"pass"}',
  'Redis 后缀匹配白名单，自动刷新'
)
ON CONFLICT (node_type, name) DO NOTHING;
