"""Concrete tool selection and wiring."""

from __future__ import annotations

import logging
import os

from app.adapters.budget import mock as mock_budget
from app.adapters.calendar import mock as mock_calendar
from app.adapters.poi import mock as mock_poi
from app.adapters.route import mock as mock_route
from app.adapters.weather import mock as mock_weather
from app.security.key_manager import get_key_manager
from app.security.redact import redact_sensitive
from app.shared.exceptions import ToolError

_logger = logging.getLogger("trip-agent.tools")
_DEFAULT_ALLOWLIST = {"poi", "route", "budget", "weather", "calendar"}


def _has_amap_key() -> bool:
    return get_key_manager().has_key("AMAP_API_KEY")


def _strict_external_enabled() -> bool:
    value = os.getenv("STRICT_EXTERNAL_DATA", "")
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _tool_allowlist() -> set[str]:
    raw = os.getenv("TOOL_ALLOWLIST", "")
    if not raw.strip():
        return set(_DEFAULT_ALLOWLIST)
    values = {item.strip().lower() for item in raw.split(",") if item.strip()}
    return values or set(_DEFAULT_ALLOWLIST)


def _ensure_tool_allowed(tool_name: str) -> None:
    if tool_name not in _tool_allowlist():
        raise ToolError(tool_name, f"Tool blocked by TOOL_ALLOWLIST: {tool_name}")


def _raise_if_strict_without_key(tool_name: str) -> None:
    if _strict_external_enabled() and not _has_amap_key():
        raise ToolError(tool_name, "STRICT_EXTERNAL_DATA=true requires AMAP_API_KEY")


def get_poi_tool():
    _ensure_tool_allowed("poi")
    _raise_if_strict_without_key("poi")
    if _has_amap_key():
        try:
            from app.adapters.poi import real as real_poi

            return real_poi
        except Exception as exc:
            if _strict_external_enabled():
                raise ToolError("poi", f"Failed to load amap adapter: {redact_sensitive(str(exc))}") from None
            _logger.warning(
                "Failed to load amap poi adapter, fallback to mock: %s",
                redact_sensitive(str(exc)),
            )
    return mock_poi


def get_route_tool():
    _ensure_tool_allowed("route")
    _raise_if_strict_without_key("route")
    if _has_amap_key():
        try:
            from app.adapters.route import real as real_route

            return real_route
        except Exception as exc:
            if _strict_external_enabled():
                raise ToolError("route", f"Failed to load amap adapter: {redact_sensitive(str(exc))}") from None
            _logger.warning(
                "Failed to load amap route adapter, fallback to mock: %s",
                redact_sensitive(str(exc)),
            )
    return mock_route


def get_budget_tool():
    _ensure_tool_allowed("budget")
    return mock_budget


def get_weather_tool():
    _ensure_tool_allowed("weather")
    _raise_if_strict_without_key("weather")
    if _has_amap_key():
        try:
            from app.adapters.weather import real as real_weather

            return real_weather
        except Exception as exc:
            if _strict_external_enabled():
                raise ToolError("weather", f"Failed to load amap adapter: {redact_sensitive(str(exc))}") from None
            _logger.warning(
                "Failed to load amap weather adapter, fallback to mock: %s",
                redact_sensitive(str(exc)),
            )
    return mock_weather


def get_calendar_tool():
    _ensure_tool_allowed("calendar")
    return mock_calendar


def _resolve_llm_provider_name() -> str:
    km = get_key_manager()
    if km.has_key("DASHSCOPE_API_KEY"):
        return "dashscope"
    if km.has_key("OPENAI_API_KEY"):
        return "openai"
    if km.has_key("LLM_API_KEY"):
        return "llm_compatible"
    return "template"


def describe_active_tools() -> dict[str, str]:
    return {
        "poi": "amap" if _has_amap_key() else "mock",
        "route": "amap" if _has_amap_key() else "mock",
        "budget": "mock",
        "weather": "amap" if _has_amap_key() else "mock",
        "calendar": "mock",
        "llm": _resolve_llm_provider_name(),
        "strict_external_data": "true" if _strict_external_enabled() else "false",
    }


__all__ = [
    "get_poi_tool",
    "get_route_tool",
    "get_budget_tool",
    "get_weather_tool",
    "get_calendar_tool",
    "describe_active_tools",
]
