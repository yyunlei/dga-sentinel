"""DGA Platform — 常量定义"""

# 默认租户
DEFAULT_TENANT = "default"

# 模型类型
MODEL_TYPE_BINARY = "binary-xgboost"
MODEL_TYPE_MULTI = "multi-cnn-attention"

# Kafka topics
TOPIC_DNS_LOGS = "dns-query-logs"
TOPIC_DGA_ALERTS = "dga-alerts"
TOPIC_AGENT_INBOX = "agent-inbox"

# ES 索引
ES_INDEX_EVENTS = "dga-events"
ES_INDEX_ALERTS = "dga-alerts"

# Redis key 前缀
REDIS_PREFIX_CHECKPOINT = "ckpt:"
REDIS_PREFIX_WHITELIST = "whitelist:"
REDIS_PREFIX_BLACKLIST = "blacklist:"
REDIS_PREFIX_CACHE = "cache:score:"
REDIS_PREFIX_RATE_LIMIT = "ratelimit:"

# 评分缓存 TTL（秒）
SCORE_CACHE_TTL = 300

# 默认阈值
DEFAULT_DGA_THRESHOLD = 0.7
