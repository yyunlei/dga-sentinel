"""
ES 8 兼容请求头。
ES 服务 8.x；客户端 9.x 默认发 compatible-with=9 导致 400，需强制请求兼容 8。
"""

ES8_HEADERS = {
    "Accept": "application/vnd.elasticsearch+json;compatible-with=8",
    "Content-Type": "application/vnd.elasticsearch+json;compatible-with=8",
}
