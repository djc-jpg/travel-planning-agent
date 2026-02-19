"""Rate limiter with in-memory default and optional Redis backend."""

from __future__ import annotations

import logging
import os
import threading
import time

from app.security.redact import redact_sensitive

try:
    import redis
except Exception:  # pragma: no cover - optional dependency
    redis = None

_logger = logging.getLogger("trip-agent.rate-limit")
_DEFAULT_PREFIX = "trip-agent:ratelimit:"


class InMemoryRateLimiter:
    """Thread-safe fixed-window limiter."""

    backend = "memory"

    def __init__(self, max_requests: int, window_seconds: int):
        self._max = max(1, int(max_requests))
        self._window = max(1, int(window_seconds))
        self._counters: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.time()
        with self._lock:
            hits = self._counters.get(key, [])
            hits = [t for t in hits if now - t < self._window]
            if len(hits) >= self._max:
                self._counters[key] = hits
                return False
            hits.append(now)
            self._counters[key] = hits
            return True


class RedisRateLimiter:
    """Redis-backed fixed-window limiter for multi-instance deployments."""

    backend = "redis"

    def __init__(
        self,
        redis_url: str,
        max_requests: int,
        window_seconds: int,
        prefix: str = _DEFAULT_PREFIX,
    ):
        if redis is None:  # pragma: no cover
            raise RuntimeError("redis package is not installed")
        self._max = max(1, int(max_requests))
        self._window = max(1, int(window_seconds))
        self._prefix = prefix
        self._client = redis.Redis.from_url(redis_url, decode_responses=True)
        self._client.ping()

    def _key(self, key: str, bucket: int) -> str:
        return f"{self._prefix}{key}:{bucket}"

    def allow(self, key: str) -> bool:
        bucket = int(time.time()) // self._window
        redis_key = self._key(key, bucket)
        count = self._client.incr(redis_key)
        if count == 1:
            self._client.expire(redis_key, self._window + 5)
        return int(count) <= self._max


def get_rate_limiter(max_requests: int, window_seconds: int):
    redis_url = os.getenv("RATE_LIMIT_REDIS_URL") or os.getenv("REDIS_URL")
    if redis_url:
        if redis is None:
            _logger.warning(
                "Rate limiter redis url is set but redis dependency is missing; fallback to memory",
            )
        else:
            try:
                limiter = RedisRateLimiter(redis_url, max_requests, window_seconds)
                _logger.info("Rate limiter initialized with Redis backend")
                return limiter
            except Exception as exc:
                _logger.warning(
                    "Failed to initialize Redis rate limiter, fallback to memory: %s",
                    redact_sensitive(str(exc)),
                )

    return InMemoryRateLimiter(max_requests=max_requests, window_seconds=window_seconds)

