"""Step2 planning constraint engine + repair engine tests."""

from __future__ import annotations

from datetime import date

from app.domain.enums import Pace
from app.domain.models import (
    Itinerary,
    ItineraryDay,
    POI,
    ScheduleItem,
    TimeSlot,
    TripConstraints,
    UserProfile,
)
from app.domain.planning.constraints import ConstraintEngine
from app.domain.planning.repair import RepairEngine


def _poi(
    pid: str,
    *,
    cluster: str,
    cost: float,
    open_hours: str = "09:00-20:00",
    requires_reservation: bool = False,
) -> POI:
    return POI(
        id=pid,
        name=f"poi-{pid}",
        city="beijing",
        lat=39.9 + int(pid[-1]) * 0.01 if pid[-1].isdigit() else 39.9,
        lon=116.4 + int(pid[-1]) * 0.01 if pid[-1].isdigit() else 116.4,
        cluster=cluster,
        duration_hours=1.5,
        cost=cost,
        ticket_price=cost,
        open_time=open_hours,
        open_hours=open_hours,
        requires_reservation=requires_reservation,
    )


def _itinerary_with_violations() -> tuple[Itinerary, TripConstraints]:
    p1 = _poi("p1", cluster="c1", cost=80, open_hours="09:00-12:00")
    p2 = _poi("p2", cluster="c2", cost=80, open_hours="09:00-12:00", requires_reservation=True)
    p3 = _poi("p3", cluster="c1", cost=80, open_hours="09:00-20:00")
    backup = _poi("p4", cluster="c2", cost=0)

    day = ItineraryDay(
        day_number=1,
        date=date(2026, 4, 1),
        schedule=[
            ScheduleItem(
                poi=p1,
                time_slot=TimeSlot.MORNING,
                start_time="10:00",
                end_time="12:00",
                travel_minutes=0.0,
                buffer_minutes=10.0,
                notes="cluster=c1",
            ),
            ScheduleItem(
                poi=p2,
                time_slot=TimeSlot.AFTERNOON,
                start_time="11:30",
                end_time="13:00",
                travel_minutes=25.0,
                buffer_minutes=10.0,
                notes="cluster=c2",
            ),
            ScheduleItem(
                poi=p3,
                time_slot=TimeSlot.EVENING,
                start_time="14:00",
                end_time="16:00",
                travel_minutes=30.0,
                buffer_minutes=10.0,
                notes="cluster=c1",
            ),
        ],
        backups=[
            ScheduleItem(
                poi=backup,
                time_slot=TimeSlot.AFTERNOON,
                is_backup=True,
                notes="backup",
            )
        ],
        total_travel_minutes=55.0,
    )
    itinerary = Itinerary(city="beijing", days=[day], total_cost=240.0)
    constraints = TripConstraints(city="beijing", days=1, pace=Pace.RELAXED, budget_per_day=100)
    return itinerary, constraints


def test_constraint_engine_detects_core_violations():
    itinerary, constraints = _itinerary_with_violations()
    engine = ConstraintEngine.default()
    violations = engine.evaluate(itinerary, constraints)
    codes = {item.code for item in violations}
    assert "TIME_CONFLICT" in codes
    assert "OVER_BUDGET" in codes
    assert "INTENSITY_OVERLOAD" in codes
    assert "OPEN_HOURS_VIOLATION" in codes
    assert "ROUTE_BACKTRACKING" in codes
    assert "RESERVATION_RISK" in codes


def test_repair_engine_uses_allowed_actions_and_reduces_violations():
    itinerary, constraints = _itinerary_with_violations()
    engine = ConstraintEngine.default()
    before = engine.evaluate(itinerary, constraints)

    result = RepairEngine(engine).repair(itinerary, constraints, profile=UserProfile())
    after = result.remaining_violations

    assert len(after) <= len(before)
    assert result.actions
    allowed = ("reorder_day", "remove_poi:", "replace_with_backup:", "increase_buffer:+5m")
    for action in result.actions:
        payload = action.split(":", 1)[1] if ":" in action else action
        assert payload.startswith(allowed)


def test_repair_engine_fixes_global_over_budget_without_day_marker():
    p1 = _poi("p1", cluster="c1", cost=120)
    p2 = _poi("p2", cluster="c1", cost=80)
    day = ItineraryDay(
        day_number=1,
        date=date(2026, 4, 2),
        schedule=[
            ScheduleItem(
                poi=p1,
                time_slot=TimeSlot.MORNING,
                start_time="09:00",
                end_time="11:00",
                travel_minutes=0.0,
                buffer_minutes=10.0,
            ),
            ScheduleItem(
                poi=p2,
                time_slot=TimeSlot.AFTERNOON,
                start_time="13:00",
                end_time="15:00",
                travel_minutes=10.0,
                buffer_minutes=10.0,
            ),
        ],
        backups=[],
    )
    itinerary = Itinerary(city="beijing", days=[day], total_cost=400.0)
    constraints = TripConstraints(city="beijing", days=1, pace=Pace.MODERATE, budget_per_day=300)
    engine = ConstraintEngine.default()

    before_codes = {item.code for item in engine.evaluate(itinerary, constraints)}
    assert "OVER_BUDGET" in before_codes

    result = RepairEngine(engine).repair(itinerary, constraints, profile=UserProfile())
    after_codes = {item.code for item in result.remaining_violations}

    assert "OVER_BUDGET" not in after_codes
    assert any("remove_poi:" in action for action in result.actions)
    assert result.itinerary.total_cost <= 300.0 + 1e-6
