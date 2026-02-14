"""Backward-compatible cache wrapper."""

from app.infrastructure.cache import MemoryCache, make_cache_key, poi_cache, route_cache, weather_cache

__all__ = ["MemoryCache", "make_cache_key", "poi_cache", "route_cache", "weather_cache"]

