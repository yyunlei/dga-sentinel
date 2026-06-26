/**
 * 各节点类型的专业配置 Schema（用于右侧抽屉表单）
 * 点击画布节点时，根据 subType 渲染对应表单项
 */
export interface NodeConfigFieldSchema {
  key: string;
  label: string;
  type: "string" | "number" | "boolean" | "enum" | "array";
  required?: boolean;
  placeholder?: string;
  default?: unknown;
  options?: { label: string; value: string }[];
}

export interface NodeConfigSchemaDef {
  label: string;
  fields: NodeConfigFieldSchema[];
}

export const NODE_CONFIG_SCHEMAS: Record<string, NodeConfigSchemaDef> = {
  // ═══════════════════════════════════════════
  //  Ingest — 数据接入
  // ═══════════════════════════════════════════
  kafka_consumer: {
    label: "Kafka 消费者",
    fields: [
      {
        key: "topic",
        label: "Kafka Topic",
        type: "string",
        required: true,
        placeholder: "dns-query-logs",
      },
      {
        key: "group_id",
        label: "Consumer Group ID",
        type: "string",
        required: true,
        placeholder: "dga-realtime-v1",
      },
      {
        key: "bootstrap_servers",
        label: "Bootstrap Servers",
        type: "string",
        required: true,
        placeholder: "kafka:9092",
        default: "kafka:9092",
      },
      {
        key: "auto_offset_reset",
        label: "Offset 重置策略",
        type: "enum",
        default: "latest",
        options: [
          { label: "latest — 从最新消息开始", value: "latest" },
          { label: "earliest — 从最早消息开始", value: "earliest" },
        ],
      },
      {
        key: "max_poll_records",
        label: "单次拉取最大条数",
        type: "number",
        default: 500,
        placeholder: "500",
      },
      {
        key: "session_timeout_ms",
        label: "会话超时 (ms)",
        type: "number",
        default: 30000,
        placeholder: "30000",
      },
      {
        key: "enable_auto_commit",
        label: "自动提交 Offset",
        type: "boolean",
        default: true,
      },
      {
        key: "value_deserializer",
        label: "消息反序列化",
        type: "enum",
        default: "json",
        options: [
          { label: "JSON", value: "json" },
          { label: "Avro", value: "avro" },
          { label: "Raw String", value: "string" },
        ],
      },
    ],
  },
  file_reader: {
    label: "文件读取",
    fields: [
      {
        key: "directory",
        label: "数据目录",
        type: "string",
        required: true,
        placeholder: "/data/dns-logs/",
      },
      {
        key: "pattern",
        label: "文件匹配模式",
        type: "string",
        placeholder: "*.jsonl",
      },
      {
        key: "format",
        label: "文件格式",
        type: "enum",
        default: "jsonl",
        options: [
          { label: "JSON Lines (.jsonl)", value: "jsonl" },
          { label: "JSON (.json)", value: "json" },
          { label: "CSV (.csv)", value: "csv" },
          { label: "Parquet (.parquet)", value: "parquet" },
        ],
      },
      {
        key: "encoding",
        label: "字符编码",
        type: "string",
        default: "utf-8",
        placeholder: "utf-8",
      },
      {
        key: "batch_size",
        label: "批量读取行数",
        type: "number",
        default: 1000,
        placeholder: "1000",
      },
      {
        key: "recursive",
        label: "递归扫描子目录",
        type: "boolean",
        default: false,
      },
      {
        key: "watch_mode",
        label: "监听新文件",
        type: "boolean",
        default: false,
      },
    ],
  },

  es_source: {
    label: "Elasticsearch 数据源",
    fields: [
      {
        key: "hosts",
        label: "ES 集群地址",
        type: "string",
        required: true,
        placeholder: "http://elasticsearch:9200",
        default: "http://elasticsearch:9200",
      },
      {
        key: "index",
        label: "索引模式",
        type: "string",
        required: true,
        placeholder: "dns-logs-*",
      },
      {
        key: "query",
        label: "查询 DSL (JSON)",
        type: "string",
        placeholder: '{"range":{"timestamp":{"gte":"now-7d"}}}',
      },
      {
        key: "scroll_size",
        label: "每次滚动条数",
        type: "number",
        default: 1000,
        placeholder: "1000",
      },
      {
        key: "scroll_timeout",
        label: "滚动超时",
        type: "string",
        default: "5m",
        placeholder: "5m",
      },
      {
        key: "fields",
        label: "返回字段",
        type: "array",
        placeholder: "domain, src_ip, timestamp",
      },
    ],
  },

  // ═══════════════════════════════════════════
  //  Transform — 数据转换
  // ═══════════════════════════════════════════
  dns_parser: {
    label: "DNS 日志解析",
    fields: [
      {
        key: "fields",
        label: "解析字段",
        type: "array",
        placeholder: "domain, src_ip, query_type, timestamp",
      },
      {
        key: "source_field",
        label: "原始数据字段",
        type: "string",
        default: "raw_message",
        placeholder: "raw_message",
      },
      {
        key: "input_format",
        label: "输入格式",
        type: "enum",
        default: "json",
        options: [
          { label: "JSON 对象", value: "json" },
          { label: "文本行 (正则解析)", value: "text" },
          { label: "Syslog", value: "syslog" },
          { label: "PCAP", value: "pcap" },
        ],
      },
      {
        key: "domain_field",
        label: "域名字段映射",
        type: "string",
        default: "query_name",
        placeholder: "query_name",
      },
      {
        key: "timestamp_field",
        label: "时间戳字段映射",
        type: "string",
        default: "timestamp",
        placeholder: "timestamp",
      },
      {
        key: "timestamp_format",
        label: "时间戳格式",
        type: "string",
        placeholder: "%Y-%m-%dT%H:%M:%S",
      },
      {
        key: "drop_invalid",
        label: "丢弃无效记录",
        type: "boolean",
        default: true,
      },
    ],
  },
  feature_extractor: {
    label: "特征提取",
    fields: [
      {
        key: "extractors",
        label: "特征提取器",
        type: "array",
        required: true,
        placeholder: "lexical, entropy, ngram, vowel_ratio, digit_ratio",
      },
      {
        key: "domain_field",
        label: "域名字段",
        type: "string",
        default: "domain",
        placeholder: "domain",
      },
      {
        key: "ngram_range",
        label: "N-Gram 范围",
        type: "string",
        default: "2,3",
        placeholder: "2,3",
      },
      {
        key: "entropy_base",
        label: "熵计算底数",
        type: "enum",
        default: "2",
        options: [
          { label: "Base 2 (bits)", value: "2" },
          { label: "Base e (nats)", value: "e" },
          { label: "Base 10 (bans)", value: "10" },
        ],
      },
      { key: "normalize", label: "特征归一化", type: "boolean", default: true },
      {
        key: "output_field",
        label: "输出字段名",
        type: "string",
        default: "features",
        placeholder: "features",
      },
    ],
  },

  severity_tag: {
    label: "严重度标记",
    fields: [
      {
        key: "critical_threshold",
        label: "CRITICAL 阈值 (>=)",
        type: "number",
        default: 0.95,
        placeholder: "0.95",
      },
      {
        key: "high_threshold",
        label: "HIGH 阈值 (>=)",
        type: "number",
        default: 0.85,
        placeholder: "0.85",
      },
      {
        key: "medium_threshold",
        label: "MEDIUM 阈值 (>=)",
        type: "number",
        default: 0.7,
        placeholder: "0.7",
      },
      {
        key: "score_field",
        label: "分数字段",
        type: "string",
        default: "score",
        placeholder: "score",
      },
      {
        key: "output_field",
        label: "输出字段",
        type: "string",
        default: "severity",
        placeholder: "severity",
      },
    ],
  },

  threat_intel_enrich: {
    label: "威胁情报富化",
    fields: [
      {
        key: "providers",
        label: "情报源",
        type: "array",
        required: true,
        placeholder: "virustotal, abuseipdb, threatfox",
      },
      {
        key: "api_key_env",
        label: "API Key 环境变量",
        type: "string",
        placeholder: "VT_API_KEY",
      },
      {
        key: "cache_ttl",
        label: "缓存 TTL (秒)",
        type: "number",
        default: 3600,
        placeholder: "3600",
      },
      {
        key: "timeout_ms",
        label: "查询超时 (ms)",
        type: "number",
        default: 5000,
        placeholder: "5000",
      },
      {
        key: "enrich_fields",
        label: "富化字段",
        type: "array",
        placeholder: "reputation, malware_family, first_seen",
      },
      {
        key: "fail_open",
        label: "查询失败时放行",
        type: "boolean",
        default: true,
      },
    ],
  },

  geoip_lookup: {
    label: "GeoIP 地理定位",
    fields: [
      {
        key: "ip_field",
        label: "IP 字段",
        type: "string",
        required: true,
        default: "src_ip",
        placeholder: "src_ip",
      },
      {
        key: "database",
        label: "GeoIP 数据库",
        type: "enum",
        default: "maxmind",
        options: [
          { label: "MaxMind GeoLite2", value: "maxmind" },
          { label: "IP2Location", value: "ip2location" },
          { label: "DB-IP", value: "dbip" },
        ],
      },
      {
        key: "db_path",
        label: "数据库文件路径",
        type: "string",
        placeholder: "/data/GeoLite2-City.mmdb",
      },
      {
        key: "output_fields",
        label: "输出字段",
        type: "array",
        placeholder: "country, city, latitude, longitude, asn",
      },
      {
        key: "high_risk_countries",
        label: "高风险国家代码",
        type: "array",
        placeholder: "RU, CN, KP, IR",
      },
    ],
  },

  risk_aggregate: {
    label: "风险聚合评分",
    fields: [
      {
        key: "dga_score_weight",
        label: "DGA 评分权重",
        type: "number",
        default: 0.4,
        placeholder: "0.4",
      },
      {
        key: "threat_intel_weight",
        label: "威胁情报权重",
        type: "number",
        default: 0.3,
        placeholder: "0.3",
      },
      {
        key: "geoip_risk_weight",
        label: "地理风险权重",
        type: "number",
        default: 0.3,
        placeholder: "0.3",
      },
      {
        key: "aggregation_method",
        label: "聚合方法",
        type: "enum",
        default: "weighted_sum",
        options: [
          { label: "加权求和", value: "weighted_sum" },
          { label: "取最大值", value: "max" },
          { label: "贝叶斯融合", value: "bayesian" },
        ],
      },
      {
        key: "output_field",
        label: "输出字段",
        type: "string",
        default: "risk_score",
        placeholder: "risk_score",
      },
    ],
  },

  // ═══════════════════════════════════════════
  //  Infer — 模型推理
  // ═══════════════════════════════════════════
  scoring_service: {
    label: "DGA 评分服务",
    fields: [
      {
        key: "endpoint",
        label: "服务地址",
        type: "string",
        required: true,
        placeholder: "http://scoring-service:8000",
        default: "http://scoring-service:8000",
      },
      {
        key: "model_id",
        label: "模型 ID",
        type: "enum",
        default: "binary-xgboost",
        options: [
          { label: "binary-xgboost (二分类)", value: "binary-xgboost" },
          {
            label: "multi-cnn-attention (多分类)",
            value: "multi-cnn-attention",
          },
        ],
      },
      {
        key: "model_version",
        label: "模型版本",
        type: "string",
        placeholder: "v1.1.0 (留空使用 production)",
      },
      {
        key: "threshold",
        label: "DGA 判定阈值",
        type: "number",
        default: 0.7,
        placeholder: "0.7",
      },
      {
        key: "timeout_ms",
        label: "推理超时 (ms)",
        type: "number",
        default: 200,
        placeholder: "200",
      },
      {
        key: "batch_size",
        label: "批量推理大小",
        type: "number",
        default: 32,
        placeholder: "32",
      },
      {
        key: "protocol",
        label: "通信协议",
        type: "enum",
        default: "http",
        options: [
          { label: "HTTP/REST", value: "http" },
          { label: "gRPC", value: "grpc" },
        ],
      },
      {
        key: "retry_count",
        label: "失败重试次数",
        type: "number",
        default: 2,
        placeholder: "2",
      },
      {
        key: "cache_enabled",
        label: "启用评分缓存",
        type: "boolean",
        default: true,
      },
      {
        key: "cache_ttl",
        label: "缓存 TTL (秒)",
        type: "number",
        default: 300,
        placeholder: "300",
      },
    ],
  },
  family_classify: {
    label: "DGA 家族分类",
    fields: [
      {
        key: "endpoint",
        label: "服务地址",
        type: "string",
        required: true,
        placeholder: "http://scoring-service:8000",
        default: "http://scoring-service:8000",
      },
      {
        key: "model_id",
        label: "模型 ID",
        type: "string",
        default: "multi-cnn-attention",
        placeholder: "multi-cnn-attention",
      },
      {
        key: "top_k",
        label: "返回 Top-K 家族",
        type: "number",
        default: 3,
        placeholder: "3",
      },
      {
        key: "min_confidence",
        label: "最低置信度",
        type: "number",
        default: 0.3,
        placeholder: "0.3",
      },
      {
        key: "timeout_ms",
        label: "推理超时 (ms)",
        type: "number",
        default: 300,
        placeholder: "300",
      },
      {
        key: "only_dga",
        label: "仅对 DGA 域名分类",
        type: "boolean",
        default: true,
      },
    ],
  },

  // ═══════════════════════════════════════════
  //  Filter — 过滤规则
  // ═══════════════════════════════════════════
  whitelist: {
    label: "白名单过滤",
    fields: [
      {
        key: "source",
        label: "白名单来源",
        type: "enum",
        required: true,
        default: "redis",
        options: [
          { label: "Redis Set", value: "redis" },
          { label: "本地文件", value: "file" },
          { label: "API 接口", value: "api" },
        ],
      },
      {
        key: "redis_key",
        label: "Redis Key",
        type: "string",
        placeholder: "whitelist:domains",
      },
      {
        key: "redis_url",
        label: "Redis 地址",
        type: "string",
        default: "redis://redis:6379",
        placeholder: "redis://redis:6379",
      },
      {
        key: "file_path",
        label: "文件路径",
        type: "string",
        placeholder: "/etc/dga/whitelist.txt",
      },
      {
        key: "domain_field",
        label: "域名字段",
        type: "string",
        default: "domain",
        placeholder: "domain",
      },
      {
        key: "match_mode",
        label: "匹配模式",
        type: "enum",
        default: "exact",
        options: [
          { label: "精确匹配", value: "exact" },
          { label: "后缀匹配 (*.example.com)", value: "suffix" },
          { label: "正则匹配", value: "regex" },
        ],
      },
      {
        key: "refresh_interval",
        label: "刷新间隔 (秒)",
        type: "number",
        default: 300,
        placeholder: "300",
      },
      {
        key: "on_match",
        label: "命中动作",
        type: "enum",
        default: "pass",
        options: [
          { label: "放行 (score=0)", value: "pass" },
          { label: "丢弃记录", value: "drop" },
          { label: "仅标记", value: "tag" },
        ],
      },
    ],
  },

  threshold: {
    label: "阈值过滤",
    fields: [
      {
        key: "min_score",
        label: "DGA 最低阈值",
        type: "number",
        required: true,
        default: 0.7,
        placeholder: "0.7",
      },
      {
        key: "score_field",
        label: "分数字段",
        type: "string",
        default: "score",
        placeholder: "score",
      },
      {
        key: "tenant_override",
        label: "支持租户级阈值覆盖",
        type: "boolean",
        default: true,
      },
      {
        key: "severity_rules",
        label: "严重度分级",
        type: "enum",
        default: "auto",
        options: [
          { label: "自动分级 (CRITICAL/HIGH/MEDIUM/LOW)", value: "auto" },
          { label: "仅二分类 (DGA/正常)", value: "binary" },
          { label: "自定义规则", value: "custom" },
        ],
      },
      {
        key: "critical_threshold",
        label: "CRITICAL 阈值",
        type: "number",
        default: 0.95,
        placeholder: "0.95",
      },
      {
        key: "high_threshold",
        label: "HIGH 阈值",
        type: "number",
        default: 0.85,
        placeholder: "0.85",
      },
      {
        key: "action_below",
        label: "低于阈值动作",
        type: "enum",
        default: "drop",
        options: [
          { label: "丢弃", value: "drop" },
          { label: "标记为正常并继续", value: "pass_normal" },
        ],
      },
    ],
  },

  blacklist: {
    label: "黑名单过滤",
    fields: [
      {
        key: "source",
        label: "黑名单来源",
        type: "enum",
        required: true,
        default: "redis",
        options: [
          { label: "Redis Set", value: "redis" },
          { label: "本地文件", value: "file" },
          { label: "威胁情报 API", value: "threat_intel" },
        ],
      },
      {
        key: "redis_key",
        label: "Redis Key",
        type: "string",
        placeholder: "blacklist:domains",
      },
      {
        key: "redis_url",
        label: "Redis 地址",
        type: "string",
        default: "redis://redis:6379",
        placeholder: "redis://redis:6379",
      },
      {
        key: "file_path",
        label: "文件路径",
        type: "string",
        placeholder: "/etc/dga/blacklist.txt",
      },
      {
        key: "domain_field",
        label: "域名字段",
        type: "string",
        default: "domain",
        placeholder: "domain",
      },
      {
        key: "on_match_score",
        label: "命中时分数",
        type: "number",
        default: 1.0,
        placeholder: "1.0",
      },
      {
        key: "on_match_severity",
        label: "命中时严重度",
        type: "enum",
        default: "CRITICAL",
        options: [
          { label: "CRITICAL", value: "CRITICAL" },
          { label: "HIGH", value: "HIGH" },
        ],
      },
      {
        key: "refresh_interval",
        label: "刷新间隔 (秒)",
        type: "number",
        default: 300,
        placeholder: "300",
      },
    ],
  },
  // ═══════════════════════════════════════════
  //  Sink — 数据输出
  // ═══════════════════════════════════════════
  es_sink: {
    label: "Elasticsearch 输出",
    fields: [
      {
        key: "hosts",
        label: "ES 集群地址",
        type: "string",
        required: true,
        placeholder: "http://elasticsearch:9200",
        default: "http://elasticsearch:9200",
      },
      {
        key: "index",
        label: "索引名",
        type: "string",
        required: true,
        placeholder: "dga-events-{date}",
        default: "dga-events",
      },
      {
        key: "index_date_pattern",
        label: "日期索引后缀",
        type: "enum",
        default: "daily",
        options: [
          { label: "按天 (-YYYY.MM.dd)", value: "daily" },
          { label: "按月 (-YYYY.MM)", value: "monthly" },
          { label: "无后缀 (固定索引)", value: "none" },
        ],
      },
      {
        key: "condition",
        label: "写入条件",
        type: "enum",
        default: "always",
        options: [
          { label: "全部写入", value: "always" },
          { label: "仅 DGA 域名 (is_dga=true)", value: "is_dga" },
          { label: "仅高危 (severity=CRITICAL|HIGH)", value: "high_severity" },
        ],
      },
      {
        key: "pipeline",
        label: "Ingest Pipeline",
        type: "string",
        placeholder: "dga-enrich-pipeline",
      },
      {
        key: "bulk_size",
        label: "批量写入条数",
        type: "number",
        default: 200,
        placeholder: "200",
      },
      {
        key: "flush_interval_ms",
        label: "刷新间隔 (ms)",
        type: "number",
        default: 5000,
        placeholder: "5000",
      },
      {
        key: "retry_on_conflict",
        label: "冲突重试次数",
        type: "number",
        default: 3,
        placeholder: "3",
      },
      {
        key: "username",
        label: "用户名",
        type: "string",
        placeholder: "elastic (留空无认证)",
      },
      {
        key: "password",
        label: "密码",
        type: "string",
        placeholder: "留空无认证",
      },
    ],
  },

  kafka_sink: {
    label: "Kafka 输出",
    fields: [
      {
        key: "topic",
        label: "输出 Topic",
        type: "string",
        required: true,
        placeholder: "dga-alerts",
        default: "dga-alerts",
      },
      {
        key: "bootstrap_servers",
        label: "Bootstrap Servers",
        type: "string",
        required: true,
        placeholder: "kafka:9092",
        default: "kafka:9092",
      },
      {
        key: "condition",
        label: "写入条件",
        type: "enum",
        default: "is_dga",
        options: [
          { label: "全部写入", value: "always" },
          { label: "仅 DGA 域名", value: "is_dga" },
          { label: "分数 >= 阈值", value: "score_threshold" },
        ],
      },
      {
        key: "score_threshold",
        label: "分数阈值 (条件为分数时)",
        type: "number",
        default: 0.7,
        placeholder: "0.7",
      },
      {
        key: "key_field",
        label: "消息 Key 字段",
        type: "string",
        default: "domain",
        placeholder: "domain",
      },
      {
        key: "value_serializer",
        label: "消息序列化",
        type: "enum",
        default: "json",
        options: [
          { label: "JSON", value: "json" },
          { label: "Avro", value: "avro" },
        ],
      },
      {
        key: "acks",
        label: "确认级别",
        type: "enum",
        default: "1",
        options: [
          { label: "0 — 不等待确认", value: "0" },
          { label: "1 — Leader 确认", value: "1" },
          { label: "all — 所有副本确认", value: "all" },
        ],
      },
      {
        key: "compression",
        label: "压缩算法",
        type: "enum",
        default: "none",
        options: [
          { label: "无压缩", value: "none" },
          { label: "gzip", value: "gzip" },
          { label: "snappy", value: "snappy" },
          { label: "lz4", value: "lz4" },
        ],
      },
      {
        key: "linger_ms",
        label: "发送延迟 (ms)",
        type: "number",
        default: 5,
        placeholder: "5",
      },
      {
        key: "batch_size",
        label: "批量大小 (bytes)",
        type: "number",
        default: 16384,
        placeholder: "16384",
      },
    ],
  },

  starrocks_sink: {
    label: "StarRocks 输出",
    fields: [
      {
        key: "fe_hosts",
        label: "FE 地址",
        type: "string",
        required: true,
        placeholder: "starrocks-fe:8030",
        default: "starrocks-fe:8030",
      },
      {
        key: "database",
        label: "数据库名",
        type: "string",
        required: true,
        placeholder: "dga_analytics",
        default: "dga_analytics",
      },
      {
        key: "table",
        label: "表名",
        type: "string",
        required: true,
        placeholder: "dga_events",
      },
      {
        key: "username",
        label: "用户名",
        type: "string",
        default: "root",
        placeholder: "root",
      },
      {
        key: "password",
        label: "密码",
        type: "string",
        placeholder: "留空无密码",
      },
      {
        key: "load_method",
        label: "导入方式",
        type: "enum",
        default: "stream_load",
        options: [
          { label: "Stream Load (实时)", value: "stream_load" },
          { label: "Insert Into (批量)", value: "insert" },
          { label: "Broker Load (大批量)", value: "broker_load" },
        ],
      },
      {
        key: "format",
        label: "数据格式",
        type: "enum",
        default: "json",
        options: [
          { label: "JSON", value: "json" },
          { label: "CSV", value: "csv" },
        ],
      },
      {
        key: "batch_size",
        label: "批量写入条数",
        type: "number",
        default: 500,
        placeholder: "500",
      },
      {
        key: "flush_interval_ms",
        label: "刷新间隔 (ms)",
        type: "number",
        default: 10000,
        placeholder: "10000",
      },
      {
        key: "max_filter_ratio",
        label: "最大容错率",
        type: "number",
        default: 0.1,
        placeholder: "0.1",
      },
      {
        key: "condition",
        label: "写入条件",
        type: "enum",
        default: "always",
        options: [
          { label: "全部写入", value: "always" },
          { label: "仅 DGA 域名", value: "is_dga" },
        ],
      },
    ],
  },

  fan_out: {
    label: "并行扇出",
    fields: [
      {
        key: "channels",
        label: "输出通道",
        type: "array",
        required: true,
        placeholder: "es, kafka, starrocks, webhook",
      },
      {
        key: "es_index",
        label: "ES 索引",
        type: "string",
        placeholder: "dga-alerts",
      },
      {
        key: "es_hosts",
        label: "ES 地址",
        type: "string",
        placeholder: "http://elasticsearch:9200",
      },
      {
        key: "kafka_topic",
        label: "Kafka Topic",
        type: "string",
        placeholder: "siem-alerts",
      },
      {
        key: "kafka_servers",
        label: "Kafka Servers",
        type: "string",
        placeholder: "kafka:9092",
      },
      {
        key: "starrocks_table",
        label: "StarRocks 表",
        type: "string",
        placeholder: "dga_alerts",
      },
      {
        key: "webhook_url",
        label: "Webhook URL",
        type: "string",
        placeholder: "http://siem:8080/api/alerts",
      },
      {
        key: "webhook_headers",
        label: "Webhook Headers (JSON)",
        type: "string",
        placeholder: '{"Authorization":"Bearer xxx"}',
      },
      {
        key: "fail_strategy",
        label: "部分失败策略",
        type: "enum",
        default: "continue",
        options: [
          { label: "继续执行其他通道", value: "continue" },
          { label: "全部中止", value: "abort" },
        ],
      },
      {
        key: "condition",
        label: "触发条件",
        type: "enum",
        default: "is_dga",
        options: [
          { label: "全部", value: "always" },
          { label: "仅 DGA", value: "is_dga" },
          { label: "仅高危", value: "high_severity" },
        ],
      },
    ],
  },

  multi_sink: {
    label: "条件多路输出",
    fields: [
      {
        key: "routes",
        label: "路由规则",
        type: "array",
        placeholder: "es:always, kafka:is_dga, starrocks:high_severity",
      },
      {
        key: "default_target",
        label: "默认输出",
        type: "enum",
        default: "es",
        options: [
          { label: "Elasticsearch", value: "es" },
          { label: "Kafka", value: "kafka" },
          { label: "StarRocks", value: "starrocks" },
          { label: "丢弃", value: "drop" },
        ],
      },
      {
        key: "es_index",
        label: "ES 索引",
        type: "string",
        placeholder: "dga-events",
      },
      {
        key: "kafka_topic",
        label: "Kafka Topic",
        type: "string",
        placeholder: "dga-alerts",
      },
      {
        key: "starrocks_table",
        label: "StarRocks 表",
        type: "string",
        placeholder: "dga_events",
      },
    ],
  },
};

export function getSchemaForNode(subType: string): NodeConfigSchemaDef | null {
  return NODE_CONFIG_SCHEMAS[subType] ?? null;
}
