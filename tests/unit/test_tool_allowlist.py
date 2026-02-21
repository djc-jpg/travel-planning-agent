"""Tool allowlist tests."""

from __future__ import annotations

import pytest

from app.adapters import tool_factory
from app.shared.exceptions import ToolError


def test_tool_allowlist(monkeypatch):
    monkeypatch.setenv("TOOL_ALLOWLIST", "calendar")

    with pytest.raises(ToolError):
        tool_factory.get_poi_tool()
    with pytest.raises(ToolError):
        tool_factory.get_route_tool()
    with pytest.raises(ToolError):
        tool_factory.get_weather_tool()
    with pytest.raises(ToolError):
        tool_factory.get_budget_tool()

    calendar_tool = tool_factory.get_calendar_tool()
    assert calendar_tool is not None


def test_tool_allowlist_default_allows_baseline(monkeypatch):
    monkeypatch.delenv("TOOL_ALLOWLIST", raising=False)
    assert tool_factory.get_calendar_tool() is not None

