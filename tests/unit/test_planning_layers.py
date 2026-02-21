"""Unit tests for split planning modules."""

from __future__ import annotations

from datetime import date

from app.domain.models import POI, TripConstraints, UserProfile
from app.domain.planning.postprocess import generate_itinerary_impl
from app.domain.planning.scheduling import assign_time_slots
from app.domain.planning.selection import prepare_candidate_pool
from app.planner.core import generate_itinerary


def _poi(
    pid: str,
    name: str,
    *,
    cost: float,
    themes: list[str] | None = None,
    indoor: bool = False,
) -> POI:
    return POI(
        id=pid,
        name=name,
        city="北京",
        lat=39.9,
        lon=116.4,
        themes=themes or [],
        duration_hours=1.5,
        cost=cost,
        indoor=indoor,
        open_time="09:00-18:00",
    )


def test_selection_prepare_candidate_pool_respects_free_and_must_visit():
    constraints = TripConstraints(
        city="北京",
        days=2,
        free_only=True,
        must_visit=["天安门"],
    )
    profile = UserProfile(themes=["历史"])
    candidates = [
        _poi("p1", "天安门", cost=0, themes=["历史"]),
        _poi("p2", "故宫", cost=60, themes=["历史"]),
        _poi("p3", "景山", cost=0, themes=["园林"]),
        _poi("p3", "景山重复", cost=0, themes=["园林"]),
    ]

    unique, daily_count, assumptions = prepare_candidate_pool(constraints, profile, candidates)

    assert daily_count >= 2
    assert all(p.cost <= 0 for p in unique)
    assert unique[0].name == "天安门"
    assert any("免费景点" in item for item in assumptions)


def test_scheduling_assign_time_slots_emits_windows_and_notes():
    pois = [
        _poi("a", "首都博物馆", cost=0, indoor=True),
        _poi("b", "景山公园", cost=2, indoor=False),
    ]

    schedule, meal_windows = assign_time_slots(
        pois,
        plan_date=date.today(),
        transport_mode="taxi",
        distance_fn=lambda *_: 2.0,
        travel_time_fn=lambda *_: 10.0,
        crowd_level="high",
    )

    assert schedule
    assert meal_windows
    assert all(item.start_time and item.end_time for item in schedule)


def test_postprocess_generate_impl_matches_core_wrapper_contract():
    constraints = TripConstraints(city="北京", days=2)
    profile = UserProfile(themes=["历史"])
    candidates = [
        _poi("p1", "天安门", cost=0, themes=["历史"]),
        _poi("p2", "故宫", cost=60, themes=["历史"]),
        _poi("p3", "景山", cost=2, themes=["园林"]),
        _poi("p4", "北海", cost=10, themes=["园林"]),
        _poi("p5", "国博", cost=0, themes=["历史"]),
        _poi("p6", "前门", cost=0, themes=["美食"]),
    ]

    impl_itinerary = generate_itinerary_impl(constraints, profile, candidates)
    core_itinerary = generate_itinerary(constraints, profile, candidates)

    assert len(impl_itinerary.days) == len(core_itinerary.days) == 2
    assert impl_itinerary.city == core_itinerary.city == "北京"
    assert impl_itinerary.summary
    assert core_itinerary.summary
    assert "executable itinerary" not in impl_itinerary.summary.lower()
    assert "第1天" in impl_itinerary.summary
    assert isinstance(core_itinerary.budget_breakdown, dict)


def test_selection_prepare_candidate_pool_respects_avoid_filter():
    constraints = TripConstraints(
        city="beijing",
        days=1,
        avoid=["museum"],
    )
    profile = UserProfile(themes=["history"])
    candidates = [
        _poi("p1", "city museum", cost=0, themes=["history"]),
        _poi("p2", "city park", cost=0, themes=["nature"]),
        _poi("p3", "old street food", cost=0, themes=["food"]),
    ]

    unique, _daily_count, assumptions = prepare_candidate_pool(constraints, profile, candidates)
    names = [poi.name for poi in unique]

    assert "city museum" not in names
    assert any(item.startswith("avoid_filtered=") for item in assumptions)
