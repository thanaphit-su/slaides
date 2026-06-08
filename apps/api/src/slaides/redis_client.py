from __future__ import annotations

from redis import asyncio as aioredis
from redis.backoff import ExponentialBackoff
from redis.exceptions import BusyLoadingError, ConnectionError, TimeoutError
from redis.retry import Retry

from .settings import get_settings


def create_redis_client() -> aioredis.Redis:
    return aioredis.from_url(
        get_settings().redis_url,
        decode_responses=True,
        health_check_interval=15,
        socket_connect_timeout=5,
        socket_keepalive=True,
        socket_timeout=10,
        retry=Retry(ExponentialBackoff(cap=1, base=0.05), retries=3),
        retry_on_error=[BusyLoadingError, ConnectionError, TimeoutError],
    )
