"""Session store with in-memory default and optional Redis backend."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any, Optional

try:
    import redis
except Exception:  # pragma: no cover - optional dependency
    redis = None

_logger = logging.getLogger("trip-agent.session")

_DEFAULT_TTL = 1800.0
_MAX_SESSIONS = 1000
_DEFAULT_PREFIX = "trip-agent:session:"


class SessionStore:
    """Thread-safe in-memory session store."""

    backend = "memory"

    def __init__(self, ttl: float = _DEFAULT_TTL, max_sessions: int = _MAX_SESSIONS):
        self._store: dict[str, tuple[dict[str, Any], float]] = {}
        self._ttl = ttl
        self._max_sessions = max_sessions
        self._lock = threading.Lock()

    def get(self, session_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            entry = self._store.get(session_id)
            if entry is None:
                return None
            data, expire_at = entry
            if time.time() > expire_at:
                del self._store[session_id]
                return None
            return data

    def save(self, session_id: str, state: dict[str, Any]) -> None:
        with self._lock:
            if len(self._store) >= self._max_sessions:
                self._cleanup_expired()
            if len(self._store) >= self._max_sessions:
                oldest = min(self._store, key=lambda k: self._store[k][1])
                del self._store[oldest]
            self._store[session_id] = (state, time.time() + self._ttl)

    def delete(self, session_id: str) -> None:
        with self._lock:
            self._store.pop(session_id, None)

    def exists(self, session_id: str) -> bool:
        with self._lock:
            entry = self._store.get(session_id)
            if entry is None:
                return False
            _, expire_at = entry
            return time.time() <= expire_at

    def _cleanup_expired(self) -> None:
        now = time.time()
        expired = [k for k, (_, exp) in self._store.items() if now > exp]
        for key in expired:
            del self._store[key]

    @property
    def active_count(self) -> int:
        now = time.time()
        with self._lock:
            return sum(1 for _, (_, exp) in self._store.items() if now <= exp)


class RedisSessionStore:
    """Redis-backed session store for multi-instance deployments."""

    backend = "redis"

    def __init__(self, redis_url: str, ttl: float = _DEFAULT_TTL, prefix: str = _DEFAULT_PREFIX):
        if redis is None:  # pragma: no cover
            raise RuntimeError("redis package is not installed")
        self._ttl = max(1, int(ttl))
        self._prefix = prefix
        self._client = redis.Redis.from_url(redis_url, decode_responses=True)
        self._client.ping()

    def _key(self, session_id: str) -> str:
        return f"{self._prefix}{session_id}"

    def get(self, session_id: str) -> Optional[dict[str, Any]]:
        raw = self._client.get(self._key(session_id))
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            self._client.delete(self._key(session_id))
            return None

    def save(self, session_id: str, state: dict[str, Any]) -> None:
        payload = json.dumps(state, ensure_ascii=False, default=str)
        self._client.setex(self._key(session_id), self._ttl, payload)

    def delete(self, session_id: str) -> None:
        self._client.delete(self._key(session_id))

    def exists(self, session_id: str) -> bool:
        return bool(self._client.exists(self._key(session_id)))

    @property
    def active_count(self) -> int:
        return len(self._client.keys(f"{self._prefix}*"))


def _build_store():
    ttl = float(os.getenv("SESSION_TTL_SECONDS", str(_DEFAULT_TTL)))
    max_sessions = int(os.getenv("SESSION_MAX_SESSIONS", str(_MAX_SESSIONS)))
    redis_url = os.getenv("REDIS_URL")

    if redis_url:
        if redis is None:
            _logger.warning("REDIS_URL is set but redis dependency is missing; fallback to memory store")
        else:
            try:
                store = RedisSessionStore(redis_url=redis_url, ttl=ttl)
                _logger.info("Session store initialized with Redis backend")
                return store
            except Exception as exc:
                _logger.warning(
                    "Failed to initialize Redis session store, fallback to memory store: %s",
                    exc,
                )

    return SessionStore(ttl=ttl, max_sessions=max_sessions)


_global_lock = threading.Lock()
_global_store = None


def get_session_store():
    global _global_store
    with _global_lock:
        if _global_store is None:
            _global_store = _build_store()
        return _global_store
