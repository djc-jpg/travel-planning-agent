import pytest

from app.adapters import tool_factory
from app.shared.exceptions import ToolError


def _clear_amap_key_cache():
    from app.security.key_manager import get_key_manager

    km = get_key_manager()
    km.reload("AMAP_API_KEY")


def _reload_key_cache(*names: str) -> None:
    from app.security.key_manager import get_key_manager

    km = get_key_manager()
    for name in names:
        km.reload(name)


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


def test_describe_active_tools_supports_llm_compatible_provider(monkeypatch):
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("LLM_API_KEY", "llm-key")
    _reload_key_cache("DASHSCOPE_API_KEY", "OPENAI_API_KEY", "LLM_API_KEY")

    tools = tool_factory.describe_active_tools()

    assert tools["llm"] == "llm_compatible"


def test_describe_active_tools_llm_provider_priority(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "llm-key")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "dashscope-key")
    _reload_key_cache("DASHSCOPE_API_KEY", "OPENAI_API_KEY", "LLM_API_KEY")

    tools = tool_factory.describe_active_tools()

    assert tools["llm"] == "dashscope"
