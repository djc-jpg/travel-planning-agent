"""Concrete tool selection and wiring."""

from __future__ import annotations

import logging

from app.adapters.budget import mock as mock_budget
from app.adapters.calendar import mock as mock_calendar
from app.adapters.poi import mock as mock_poi
from app.adapters.route import mock as mock_route
from app.adapters.weather import mock as mock_weather
from app.security.key_manager import get_key_manager

_logger = logging.getLogger("trip-agent.tools")


def _has_amap_key() -> bool:
    return get_key_manager().has_key("AMAP_API_KEY")


def get_poi_tool():
    if _has_amap_key():
        try:
            from app.adapters.poi import real as real_poi

            return real_poi
        except Exception as exc:
            _logger.warning("Failed to load amap poi adapter, fallback to mock: %s", exc)
    return mock_poi


def get_route_tool():
    if _has_amap_key():
        try:
            from app.adapters.route import real as real_route

            return real_route
        except Exception as exc:
            _logger.warning("Failed to load amap route adapter, fallback to mock: %s", exc)
    return mock_route


def get_budget_tool():
    return mock_budget


def get_weather_tool():
    if _has_amap_key():
        try:
            from app.adapters.weather import real as real_weather

            return real_weather
        except Exception as exc:
            _logger.warning("Failed to load amap weather adapter, fallback to mock: %s", exc)
    return mock_weather


def get_calendar_tool():
    return mock_calendar


def describe_active_tools() -> dict[str, str]:
    km = get_key_manager()
    return {
        "poi": "amap" if _has_amap_key() else "mock",
        "route": "amap" if _has_amap_key() else "mock",
        "budget": "mock",
        "weather": "amap" if _has_amap_key() else "mock",
        "calendar": "mock",
        "llm": "dashscope"
        if km.has_key("DASHSCOPE_API_KEY")
        else ("openai" if km.has_key("OPENAI_API_KEY") else "template"),
    }


__all__ = [
    "get_poi_tool",
    "get_route_tool",
    "get_budget_tool",
    "get_weather_tool",
    "get_calendar_tool",
    "describe_active_tools",
]
