"""Repair 循环测试"""

from app.agent.nodes.repair import repair_node
from app.agent.nodes.validate import validate_node
from app.domain.models import (
    Itinerary,
    ItineraryDay,
    POI,
    Pace,
    ScheduleItem,
    TimeSlot,
    TripConstraints,
)


def _make_over_budget_itinerary() -> dict:
    """构造一个明显超预算的行程"""
    items = [
        ScheduleItem(
            poi=POI(
                id=f"exp{i}", name=f"高消费景点{i}", city="北京",
                lat=39.9, lon=116.4, cost=500, duration_hours=2.0,
            ),
            time_slot=TimeSlot.MORNING,
        )
        for i in range(3)
    ]
    # 3个景点 × 500元 + 2段交通 × 5元 = 1510元
    day_cost = 500 * 3 + 2 * 5
    it = Itinerary(
        city="北京",
        days=[ItineraryDay(day_number=1, schedule=items, estimated_cost=day_cost)],
        total_cost=day_cost,
    )
    return it.model_dump(mode="json")


def test_repair_converges():
    """修复应在 max_repair_attempts 内收敛或降级"""
    state = {
        "itinerary_draft": _make_over_budget_itinerary(),
        "trip_constraints": TripConstraints(
            city="北京", days=1, budget_per_day=200, pace=Pace.MODERATE,
        ).model_dump(mode="json"),
        "user_profile": {},
        "repair_attempts": 0,
        "max_repair_attempts": 3,
        "validation_issues": [],
    }

    for _ in range(5):
        val_result = validate_node(state)
        state.update(val_result)

        issues = state.get("validation_issues", [])
        high_issues = [i for i in issues if (i.get("severity") if isinstance(i, dict) else i.severity) == "high"]

        if not high_issues:
            break

        rep_result = repair_node(state)
        state.update(rep_result)

    assert state["repair_attempts"] <= 3 + 1  # 最多 3 次修复 + 1 次降级
