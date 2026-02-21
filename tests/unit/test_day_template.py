"""Day template regression tests for itinerary realism."""

from __future__ import annotations

from app.domain.enums import Pace
from app.domain.models import POI, TripConstraints, UserProfile
from app.domain.planning.day_template import infer_poi_activity_bucket, resolve_day_template
from app.domain.planning.postprocess import generate_itinerary_impl


def _poi(
    pid: str,
    name: str,
    *,
    themes: list[str],
    lat: float,
    lon: float,
    duration_hours: float = 1.5,
) -> POI:
    return POI(
        id=pid,
        name=name,
        city="demo",
        themes=themes,
        lat=lat,
        lon=lon,
        duration_hours=duration_hours,
        open_time="09:00-20:00",
        source_category="scenic",
    )


def _main_buckets(itinerary) -> list[str]:
    day = itinerary.days[0]
    return [infer_poi_activity_bucket(item.poi) for item in day.schedule if not item.is_backup]


def test_day_template_prevents_all_museum_day_when_pool_is_diverse():
    constraints = TripConstraints(city="demo", days=1, pace=Pace.MODERATE)
    profile = UserProfile(themes=["museum"])
    candidates = [
        _poi("m1", "City Museum A", themes=["museum"], lat=30.001, lon=120.001),
        _poi("m2", "City Museum B", themes=["museum"], lat=30.002, lon=120.002),
        _poi("m3", "City Museum C", themes=["museum"], lat=30.003, lon=120.003),
        _poi("p1", "Central Park", themes=["nature"], lat=30.004, lon=120.004),
        _poi("f1", "Old Street Food Market", themes=["food"], lat=30.005, lon=120.005),
    ]

    itinerary = generate_itinerary_impl(constraints, profile, candidates)
    buckets = _main_buckets(itinerary)

    assert buckets
    assert not all(bucket == "museum" for bucket in buckets)
    assert len(set(buckets)) >= 2


def test_day_template_includes_food_stop_when_food_theme_requested():
    constraints = TripConstraints(city="demo", days=1, pace=Pace.MODERATE)
    profile = UserProfile(themes=["food"])
    candidates = [
        _poi("m1", "History Museum A", themes=["museum"], lat=31.001, lon=121.001),
        _poi("m2", "History Museum B", themes=["museum"], lat=31.002, lon=121.002),
        _poi("m3", "History Museum C", themes=["museum"], lat=31.003, lon=121.003),
        _poi("f1", "Night Food Market", themes=["food", "night"], lat=31.004, lon=121.004),
    ]

    itinerary = generate_itinerary_impl(constraints, profile, candidates)
    buckets = _main_buckets(itinerary)

    assert "food" in buckets


def test_day_template_detects_chinese_food_and_night_themes():
    constraints = TripConstraints(city="demo", days=1, pace=Pace.MODERATE)
    profile = UserProfile(
        themes=[
            "\u7f8e\u98df\u591c\u5e02",
            "\u57ce\u5e02\u591c\u666f",
        ]
    )

    template = resolve_day_template(constraints, profile, daily_count=3)

    assert template.prefer_food is True
    assert template.prefer_night is True
