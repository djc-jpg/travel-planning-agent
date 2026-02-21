"""Routing provider transparency tests."""

from __future__ import annotations

from datetime import datetime

import app.planner.routing_provider as rp
from app.domain.models import POI
from app.tools.interfaces import RouteResult


def _poi(pid: str) -> POI:
    return POI(
        id=pid,
        name=f"poi-{pid}",
        city="北京",
        lat=39.9,
        lon=116.4,
        open_time="09:00-20:00",
    )


def test_real_provider_fallback_is_transparent(monkeypatch):
    class _FailRouteTool:
        @staticmethod
        def estimate_route(_params):
            raise RuntimeError("route backend down")

    monkeypatch.setattr(rp, "get_route_tool", lambda: _FailRouteTool)
    provider = rp.RealMapRoutingProvider(fallback=rp.FixtureRoutingProvider())
    origin = _poi("a")
    destination = _poi("b")
    dep = datetime(2026, 5, 1, 8, 0)

    minutes = provider.get_travel_time(origin, destination, "public_transit", departure_time=dep)
    confidence = provider.get_confidence(origin, destination, "public_transit", departure_time=dep)
    source = provider.get_route_source(origin, destination, "public_transit")
    diagnostics = provider.get_diagnostics()

    assert minutes > 0.0
    assert source == "fallback_fixture"
    assert 0.3 <= confidence <= 0.45
    assert provider.get_fallback_count() == 1
    assert diagnostics["fallback_count"] == 1
    assert diagnostics["events"]
    assert diagnostics["events"][0]["routing_source"] == "fallback_fixture"


def test_real_provider_without_failure_uses_real_source(monkeypatch):
    class _OkRouteTool:
        @staticmethod
        def estimate_route(_params):
            return RouteResult(distance_km=5.0, duration_minutes=15.0)

    monkeypatch.setattr(rp, "get_route_tool", lambda: _OkRouteTool)
    provider = rp.RealMapRoutingProvider(fallback=rp.FixtureRoutingProvider())
    origin = _poi("a")
    destination = _poi("b")
    dep = datetime(2026, 5, 1, 11, 0)

    provider.get_travel_time(origin, destination, "public_transit", departure_time=dep)
    confidence = provider.get_confidence(origin, destination, "public_transit", departure_time=dep)

    assert provider.get_route_source(origin, destination, "public_transit") == "real"
    assert confidence > 0.45
    assert provider.get_fallback_count() == 0
    assert provider.get_diagnostics()["events"] == []


def test_build_routing_provider_prefers_real_when_amap_key_exists(monkeypatch):
    class _OkRouteTool:
        @staticmethod
        def estimate_route(_params):
            return RouteResult(distance_km=5.0, duration_minutes=12.0)

    monkeypatch.delenv("ROUTING_PROVIDER", raising=False)
    monkeypatch.setenv("AMAP_API_KEY", "amap-key")
    monkeypatch.setattr(rp, "get_route_tool", lambda: _OkRouteTool)

    provider = rp.build_routing_provider()
    assert isinstance(provider, rp.RealMapRoutingProvider)
