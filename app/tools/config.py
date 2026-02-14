"""Backward-compatible tool configuration wrapper."""


def get_poi_tool():
    from app.adapters.tool_factory import get_poi_tool as impl

    return impl()


def get_route_tool():
    from app.adapters.tool_factory import get_route_tool as impl

    return impl()


def get_budget_tool():
    from app.adapters.tool_factory import get_budget_tool as impl

    return impl()


def get_weather_tool():
    from app.adapters.tool_factory import get_weather_tool as impl

    return impl()


def get_calendar_tool():
    from app.adapters.tool_factory import get_calendar_tool as impl

    return impl()


def describe_active_tools():
    from app.adapters.tool_factory import describe_active_tools as impl

    return impl()


__all__ = [
    "get_poi_tool",
    "get_route_tool",
    "get_budget_tool",
    "get_weather_tool",
    "get_calendar_tool",
    "describe_active_tools",
]
