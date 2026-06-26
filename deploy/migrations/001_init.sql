-- DGA Platform — Migration 001: Initial Schema
-- Tables: feedback, audit_log, pipeline_configs, model_versions

-- 模型注册表
CREATE TABLE IF NOT EXISTS model_versions (
    id              SERIAL PRIMARY KEY,
    model_id        VARCHAR(64) NOT NULL,
    version         VARCHAR(32) NOT NULL,
    artifact_path   TEXT NOT NULL,
    metrics         JSONB DEFAULT '{}',
    status          VARCHAR(16) DEFAULT 'staging',
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
    mode            VARCHAR(16) NOT NULL,
    yaml_content    TEXT NOT NULL,
    status          VARCHAR(16) DEFAULT 'stopped',
    version         VARCHAR(32) DEFAULT '1.0.0',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- 反馈标注表
CREATE TABLE IF NOT EXISTS feedback (
    id              SERIAL PRIMARY KEY,
    event_id        VARCHAR(64),
    domain          VARCHAR(253),
    true_label      VARCHAR(32),
    predicted_label VARCHAR(32),
    score           REAL,
    annotator       VARCHAR(64),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

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
