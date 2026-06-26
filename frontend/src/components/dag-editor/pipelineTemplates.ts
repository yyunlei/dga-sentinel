export interface PipelineTemplate {
  key: string;
  label: string;
  description: string;
  mode: "stream" | "batch";
  nodeCount: number;
  yaml: string;
}

export const PIPELINE_TEMPLATES: PipelineTemplate[] = [
  {
    key: "blank",
    label: "空白模板",
    description: "从零开始，在可视化编辑器中自由搭建流水线",
    mode: "stream",
    nodeCount: 0,
    yaml: "nodes: []",
  },
  {
    key: "dga_realtime",
    label: "DGA 实时检测",
    description:
      "Kafka 接入 → DNS 解析 → 特征提取 → 模型推理 → 白名单过滤 → 阈值判定 → ES 存储",
    mode: "stream",
    nodeCount: 7,
    yaml: `nodes:
  - id: ingest
    type: kafka_consumer
    config:
      topic: dns-query-logs
      group_id: dga-detector-v1
      auto_offset_reset: latest
  - id: parse
    type: dns_parser
    config:
      fields: [query_name, query_type, src_ip, timestamp]
  - id: feature
    type: feature_extractor
    config:
      extractors: [lexical, entropy]
  - id: infer
    type: scoring_service
    config:
      endpoint: "http://scoring-service:8001"
      protocol: http
      timeout_ms: 500
  - id: whitelist
    type: whitelist
    config:
      source: redis
      redis_key: whitelist:domains
  - id: threshold
    type: threshold
    config:
      min_score: 0.7
  - id: sink
    type: es_sink
    config:
      hosts: "http://elasticsearch:9200"
      index: dga-events
connections:
  - { source: ingest, target: parse }
  - { source: parse, target: feature }
  - { source: feature, target: infer }
  - { source: infer, target: whitelist }
  - { source: whitelist, target: threshold }
  - { source: threshold, target: sink }`,
  },
  {
    key: "dga_batch",
    label: "DGA 批量检测",
    description:
      "文件读取 → DNS 解析 → 特征提取 → 模型推理 → 家族分类 → StarRocks 存储",
    mode: "batch",
    nodeCount: 6,
    yaml: `nodes:
  - id: source
    type: file_reader
    config:
      directory: /data/dns-logs/
      format: jsonl
      batch_size: 1000
  - id: parse
    type: dns_parser
    config:
      fields: [query_name, query_type, src_ip, timestamp]
  - id: feature
    type: feature_extractor
    config:
      extractors: [lexical, entropy, ngram]
  - id: infer
    type: scoring_service
    config:
      endpoint: "http://scoring-service:8001"
      model_id: binary-xgboost
      batch_size: 64
  - id: classify
    type: family_classify
    config:
      endpoint: "http://scoring-service:8001"
      top_k: 3
  - id: sink
    type: starrocks_sink
    config:
      fe_hosts: "starrocks-fe:8030"
      database: dga_analytics
      table: dga_events
connections:
  - { source: source, target: parse }
  - { source: parse, target: feature }
  - { source: feature, target: infer }
  - { source: infer, target: classify }
  - { source: classify, target: sink }`,
  },
  {
    key: "dns_tunnel",
    label: "DNS 隧道检测",
    description:
      "Kafka 接入 → DNS 解析 → 特征提取 → 模型推理 → GeoIP → 威胁情报 → 严重度标记 → 多路输出",
    mode: "stream",
    nodeCount: 8,
    yaml: `nodes:
  - id: ingest
    type: kafka_consumer
    config:
      topic: dns-query-logs
      group_id: dns-tunnel-v1
      auto_offset_reset: latest
  - id: parse
    type: dns_parser
    config:
      fields: [query_name, query_type, src_ip, timestamp]
  - id: feature
    type: feature_extractor
    config:
      extractors: [lexical, entropy, ngram, vowel_ratio, digit_ratio]
  - id: infer
    type: scoring_service
    config:
      endpoint: "http://scoring-service:8001"
      threshold: 0.8
  - id: geoip
    type: geoip_lookup
    config:
      ip_field: src_ip
      database: maxmind
  - id: threat_intel
    type: threat_intel_enrich
    config:
      providers: [virustotal, threatfox]
      cache_ttl: 3600
  - id: severity
    type: severity_tag
    config:
      critical_threshold: 0.95
      high_threshold: 0.85
      medium_threshold: 0.7
  - id: sink
    type: fan_out
    config:
      channels: [es, kafka]
      es_index: dns-tunnel-alerts
      kafka_topic: siem-alerts
      condition: is_dga
connections:
  - { source: ingest, target: parse }
  - { source: parse, target: feature }
  - { source: feature, target: infer }
  - { source: infer, target: geoip }
  - { source: geoip, target: threat_intel }
  - { source: threat_intel, target: severity }
  - { source: severity, target: sink }`,
  },
];
