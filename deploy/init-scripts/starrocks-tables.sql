-- DGA Platform — StarRocks 分析表初始化
-- 在 StarRocks FE 上执行: mysql -h 127.0.0.1 -P 9030 -u root < starrocks-tables.sql

CREATE DATABASE IF NOT EXISTS dga_analytics;
USE dga_analytics;

-- DGA 事件分析表（按天分区）
CREATE TABLE IF NOT EXISTS dga_events (
    event_id        VARCHAR(64),
    trace_id        VARCHAR(64),
    event_time      DATETIME NOT NULL,
    domain          VARCHAR(512) NOT NULL,
    src_ip          VARCHAR(64),
    score           DOUBLE,
    is_dga          BOOLEAN,
    family          VARCHAR(64),
    family_confidence DOUBLE,
    model_version   VARCHAR(32),
    pipeline_id     VARCHAR(128),
    tenant_id       VARCHAR(64),
    severity        VARCHAR(16)
)
DUPLICATE KEY(event_id, trace_id)
PARTITION BY RANGE(event_time) ()
DISTRIBUTED BY HASH(domain) BUCKETS 8
PROPERTIES (
    "dynamic_partition.enable" = "true",
    "dynamic_partition.time_unit" = "DAY",
    "dynamic_partition.start" = "-30",
    "dynamic_partition.end" = "3",
    "dynamic_partition.prefix" = "p",
    "replication_num" = "1"
);

-- TopN 聚合视图
CREATE TABLE IF NOT EXISTS dga_top_domains (
    stat_date       DATE NOT NULL,
    domain          VARCHAR(512) NOT NULL,
    hit_count       BIGINT,
    avg_score       DOUBLE,
    max_score       DOUBLE,
    families        VARCHAR(1024),
    src_ip_count    BIGINT
)
DUPLICATE KEY(stat_date, domain)
DISTRIBUTED BY HASH(domain) BUCKETS 4
PROPERTIES ("replication_num" = "1");
