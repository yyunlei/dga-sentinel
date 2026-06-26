"""
Gateway — 数据库连接管理
统一管理 asyncpg (PostgreSQL) + AsyncElasticsearch + Redis 连接
以及应用级共享 httpx 客户端（ES 查询池化专用）
"""
from __future__ import annotations

from fastapi import FastAPI, Request
import asyncpg
from elasticsearch import AsyncElasticsearch
import httpx
import redis.asyncio as aioredis

from common.config import get_settings
from common.observability import get_logger
from common.utils.es_compat import ES8_HEADERS

logger = get_logger(__name__)


async def init_db(app: FastAPI) -> None:
    """Initialize database connections on startup."""
    settings = get_settings()

    # PostgreSQL connection pool
    try:
        app.state.pg_pool = await asyncpg.create_pool(
            dsn=settings.pg_dsn,
            min_size=2,
            max_size=10,
            command_timeout=10,
        )
        logger.info("pg_pool_created")
    except Exception as e:
        logger.warning("pg_pool_failed", error=str(e))
        app.state.pg_pool = None

    # Elasticsearch async client（ES 服务 8.17，若客户端为 9.x 会发 compatible-with=9 导致 400，强制请求兼容 8）
    try:
        app.state.es_client = AsyncElasticsearch(
            hosts=settings.es_hosts.split(","),
            request_timeout=10,
            headers=ES8_HEADERS,
        )
        logger.info("es_client_created")
    except Exception as e:
        logger.warning("es_client_failed", error=str(e))
        app.state.es_client = None

    # Redis async client
    try:
        app.state.redis_client = aioredis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=5,
        )
        await app.state.redis_client.ping()
        logger.info("redis_client_created")
    except Exception as e:
        logger.warning("redis_client_failed", error=str(e))
        app.state.redis_client = None

    # Shared pooled httpx client for ES queries (replaces per-call AsyncClient churn)
    try:
        app.state.es_http = httpx.AsyncClient(
            timeout=httpx.Timeout(10.0),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
        logger.info("es_http_created")
    except Exception as e:
        logger.warning("es_http_failed", error=str(e))
        app.state.es_http = None


async def close_db(app: FastAPI) -> None:
    """Close database connections on shutdown."""
    if getattr(app.state, "pg_pool", None):
        await app.state.pg_pool.close()
        logger.info("pg_pool_closed")

    if getattr(app.state, "es_client", None):
        await app.state.es_client.close()
        logger.info("es_client_closed")

    if getattr(app.state, "redis_client", None):
        await app.state.redis_client.close()
        logger.info("redis_client_closed")

    if getattr(app.state, "es_http", None):
        await app.state.es_http.aclose()
        logger.info("es_http_closed")


def get_pg_pool(request: Request) -> asyncpg.Pool | None:
    """FastAPI dependency to get PostgreSQL pool."""
    return getattr(request.app.state, "pg_pool", None)


def get_es_client(request: Request) -> AsyncElasticsearch | None:
    """FastAPI dependency to get Elasticsearch client."""
    return getattr(request.app.state, "es_client", None)


def get_redis_client(request: Request):
    """FastAPI dependency to get Redis client."""
    return getattr(request.app.state, "redis_client", None)


def get_es_http(request: Request) -> httpx.AsyncClient | None:
    """FastAPI dependency to get shared ES httpx client (pooled, app-level)."""
    return getattr(request.app.state, "es_http", None)
