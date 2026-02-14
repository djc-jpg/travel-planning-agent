"""验证器测试"""

from app.domain.models import (
    Itinerary,
    ItineraryDay,
    POI,
    Pace,
    ScheduleItem,
    TimeSlot,
    TripConstraints,
)
from app.validators import run_all_validators


def _make_poi(name: str, cost: float = 0, duration: float = 1.5, **kw) -> POI:
    return POI(id=name, name=name, city="北京", cost=cost, duration_hours=duration, **kw)


def test_over_time():
    """6 个耗时景点应触发 OVER_TIME"""
    items = [
        ScheduleItem(poi=_make_poi(f"p{i}", duration=3.0), time_slot=TimeSlot.MORNING)
        for i in range(6)
    ]
    itinerary = Itinerary(
        city="北京",
        days=[ItineraryDay(day_number=1, schedule=items)],
    )
    constraints = TripConstraints(city="北京", days=1)
    issues = run_all_validators(itinerary, constraints)
    codes = [i.code for i in issues]
    assert "OVER_TIME" in codes


def test_over_budget():
    """高消费景点应触发 OVER_BUDGET"""
    items = [
        ScheduleItem(poi=_make_poi(f"p{i}", cost=200), time_slot=TimeSlot.MORNING)
        for i in range(3)
    ]
    itinerary = Itinerary(
        city="北京",
        days=[ItineraryDay(day_number=1, schedule=items, estimated_cost=600)],
        total_cost=600.0,
    )
    constraints = TripConstraints(city="北京", days=1, budget_per_day=100)
    issues = run_all_validators(itinerary, constraints)
    codes = [i.code for i in issues]
    assert "OVER_BUDGET" in codes


def test_pace_mismatch():
    """轻松节奏放 5 个景点应触发 PACE_MISMATCH"""
    items = [
        ScheduleItem(poi=_make_poi(f"p{i}", duration=1.0), time_slot=TimeSlot.MORNING)
        for i in range(5)
    ]
    itinerary = Itinerary(
        city="北京",
        days=[ItineraryDay(day_number=1, schedule=items)],
    )
    constraints = TripConstraints(city="北京", days=1, pace=Pace.RELAXED)
    issues = run_all_validators(itinerary, constraints)
    codes = [i.code for i in issues]
    assert "PACE_MISMATCH" in codes


def test_missing_backup():
    """没有备选应触发 MISSING_BACKUP"""
    items = [ScheduleItem(poi=_make_poi("p1"), time_slot=TimeSlot.MORNING)]
    itinerary = Itinerary(
        city="北京",
        days=[ItineraryDay(day_number=1, schedule=items, backups=[])],
    )
    constraints = TripConstraints(city="北京", days=1)
    issues = run_all_validators(itinerary, constraints)
    codes = [i.code for i in issues]
    assert "MISSING_BACKUP" in codes
