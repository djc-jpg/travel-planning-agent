"""Thread-safe in-memory cache with TTL and simple eviction."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from typing import Any, Optional


class MemoryCache:
    def __init__(self, default_ttl: float = 300.0, max_size: int = 500):
        self._store: dict[str, tuple[Any, float]] = {}
        self._default_ttl = default_ttl
        self._max_size = max_size
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self._misses += 1
                return None
            value, expire_at = entry
            if time.time() > expire_at:
                del self._store[key]
                self._misses += 1
                return None
            self._hits += 1
            return value

    def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        ttl = ttl if ttl is not None else self._default_ttl
        with self._lock:
            if len(self._store) >= self._max_size:
                items = sorted(self._store.items(), key=lambda x: x[1][1])
                for k, _ in items[: self._max_size // 10 + 1]:
                    del self._store[k]
            self._store[key] = (value, time.time() + ttl)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
            self._hits = 0
            self._misses = 0

    @property
    def stats(self) -> dict[str, Any]:
        total = self._hits + self._misses
        return {
            "size": len(self._store),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self._hits / total, 3) if total > 0 else 0.0,
        }


def make_cache_key(*parts: Any) -> str:
    raw = json.dumps(parts, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.md5(raw.encode()).hexdigest()


poi_cache = MemoryCache(default_ttl=600.0, max_size=200)
route_cache = MemoryCache(default_ttl=1800.0, max_size=300)
weather_cache = MemoryCache(default_ttl=3600.0, max_size=100)

