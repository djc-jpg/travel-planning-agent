"""Step1 quality tests: executability, duration fallback, ordering, and clusters."""

from __future__ import annotations

from datetime import date

from app.domain.models import POI, TripConstraints, UserProfile
from app.domain.planning.buffer import DAY_MAX_MINUTES
from app.domain.planning.cluster import build_cluster_map, enforce_day_cluster_cap
from app.domain.planning.ordering import optimize_daily_order, route_distance_km
from app.domain.planning.postprocess import generate_itinerary_impl
from app.domain.planning.scheduling import assign_time_slots, resolve_duration_minutes


def _poi(
    pid: str,
    *,
    lat: float,
    lon: float,
    cluster: str = "",
    duration_hours: float = 1.5,
    themes: list[str] | None = None,
) -> POI:
    return POI(
        id=pid,
        name=f"poi-{pid}",
        city="beijing",
        lat=lat,
        lon=lon,
        cluster=cluster,
        duration_hours=duration_hours,
        themes=themes or [],
        open_time="09:00-20:00",
    )


def _to_minutes(text: str) -> int:
    hh, mm = text.split(":")
    return int(hh) * 60 + int(mm)


def test_default_duration_fallback_for_missing_duration():
    poi = _poi("museum", lat=39.9, lon=116.4, duration_hours=0.0, themes=["museum"])
    assert resolve_duration_minutes(poi) == 120.0


def test_assign_time_slots_no_conflict_and_daily_limit():
    pois = [
        _poi("a", lat=39.90, lon=116.40),
        _poi("b", lat=39.91, lon=116.41),
        _poi("c", lat=39.92, lon=116.42),
    ]
    schedule, _meals = assign_time_slots(
        pois,
        plan_date=date(2026, 4, 1),
        transport_mode="public_transit",
        distance_fn=lambda *_: 3.0,
        travel_time_fn=lambda *_: 15.0,
        crowd_level="high",
        holiday_hint="spring_festival",
    )
    assert schedule
    for item in schedule:
        assert item.travel_minutes >= 0.0
        assert item.buffer_minutes >= 8.0
    for idx in range(1, len(schedule)):
        prev_end = _to_minutes(schedule[idx - 1].end_time or "00:00")
        curr_start = _to_minutes(schedule[idx].start_time or "00:00")
        assert curr_start >= prev_end
    span = _to_minutes(schedule[-1].end_time or "00:00") - _to_minutes(schedule[0].start_time or "00:00")
    assert span <= DAY_MAX_MINUTES


def test_ordering_2opt_reduces_or_keeps_route_distance():
    pois = [
        _poi("1", lat=0.0, lon=0.0),
        _poi("2", lat=0.0, lon=3.0),
        _poi("3", lat=3.0, lon=0.0),
        _poi("4", lat=3.0, lon=3.0),
        _poi("5", lat=1.5, lon=1.5),
    ]
    distance_fn = lambda a, b, c, d: abs(a - c) + abs(b - d)
    optimized = optimize_daily_order(pois, distance_fn=distance_fn)
    before = route_distance_km(pois, distance_fn=distance_fn)
    after = route_distance_km(optimized, distance_fn=distance_fn)
    assert after <= before + 1e-6


def test_cluster_cap_limits_day_to_two_clusters():
    pois = [
        _poi("a", lat=39.90, lon=116.40, cluster="c1"),
        _poi("b", lat=39.91, lon=116.41, cluster="c1"),
        _poi("c", lat=39.95, lon=116.45, cluster="c2"),
        _poi("d", lat=39.99, lon=116.49, cluster="c3"),
    ]
    cluster_map = build_cluster_map(pois, distance_fn=lambda a, b, c, d: abs(a - c) + abs(b - d))
    filtered, allowed = enforce_day_cluster_cap(pois, cluster_map=cluster_map, max_clusters=2)
    clusters = {cluster_map.get(poi.id, "") for poi in filtered}
    assert len(clusters) <= 2
    assert clusters.issubset(allowed)


def test_generate_impl_keeps_each_day_clusters_within_two():
    constraints = TripConstraints(city="beijing", days=2)
    profile = UserProfile(themes=["museum"])
    pois = [
        _poi("a", lat=39.90, lon=116.40, cluster="c1"),
        _poi("b", lat=39.91, lon=116.41, cluster="c1"),
        _poi("c", lat=39.95, lon=116.45, cluster="c2"),
        _poi("d", lat=39.99, lon=116.49, cluster="c3"),
        _poi("e", lat=39.92, lon=116.42, cluster="c2"),
        _poi("f", lat=39.93, lon=116.43, cluster="c3"),
    ]
    itinerary = generate_itinerary_impl(constraints, profile, pois)
    for day in itinerary.days:
        clusters = {item.poi.cluster for item in day.schedule if item.poi.cluster}
        assert len(clusters) <= 2
        assert all(item.buffer_minutes >= 0 for item in day.schedule)
