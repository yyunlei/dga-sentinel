"""
ES 索引命名工具函数。
"""
from datetime import datetime, timezone

from common.constants import ES_INDEX_EVENTS


def events_index_today() -> str:
    """当日索引名（score 写入用）"""
    return f"{ES_INDEX_EVENTS}-{datetime.now(timezone.utc).strftime('%Y.%m.%d')}"


def events_index_wildcard() -> str:
    """通配符索引名，查询跨多天数据"""
    return f"{ES_INDEX_EVENTS}-*"
