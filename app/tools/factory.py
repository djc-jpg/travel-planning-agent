"""Tool factory abstractions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolFactory:
    """Abstract holder for concrete tool providers."""

    get_poi_tool: Any
    get_route_tool: Any
    get_budget_tool: Any
    get_weather_tool: Any
    get_calendar_tool: Any

