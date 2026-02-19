import pytest

from app.adapters import tool_factory
from app.shared.exceptions import ToolError


def _clear_amap_key_cache():
    from app.security.key_manager import get_key_manager

    km = get_key_manager()
    km.reload("AMAP_API_KEY")


def test_tool_factory_allows_mock_when_not_strict(monkeypatch):
    monkeypatch.delenv("STRICT_EXTERNAL_DATA", raising=False)
    monkeypatch.delenv("AMAP_API_KEY", raising=False)
    _clear_amap_key_cache()

    poi_tool = tool_factory.get_poi_tool()
    route_tool = tool_factory.get_route_tool()
    weather_tool = tool_factory.get_weather_tool()

    assert poi_tool.__name__.endswith(".mock")
    assert route_tool.__name__.endswith(".mock")
    assert weather_tool.__name__.endswith(".mock")


def test_tool_factory_requires_amap_key_when_strict(monkeypatch):
    monkeypatch.setenv("STRICT_EXTERNAL_DATA", "true")
    monkeypatch.delenv("AMAP_API_KEY", raising=False)
    _clear_amap_key_cache()

    with pytest.raises(ToolError):
        tool_factory.get_poi_tool()
    with pytest.raises(ToolError):
        tool_factory.get_route_tool()
    with pytest.raises(ToolError):
        tool_factory.get_weather_tool()

