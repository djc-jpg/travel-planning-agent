"""Quality regression tests for Beijing 4-day Spring Festival scenario."""

from __future__ import annotations

from app.application.graph.workflow import compile_graph
from app.application.state_factory import make_initial_state
from app.domain.models import Itinerary

_CASE_INPUT = (
    "请做一个北京4日春节行程：2位成人，历史文化为主，"
    "住东城区，公共交通，希望可执行且少折返。"
)


def _run_case() -> Itinerary:
    state = make_initial_state()
    state["messages"] = [{"role": "user", "content": _CASE_INPUT}]
    result = compile_graph().invoke(state)
    assert result.get("status") == "done"
    return Itinerary.model_validate(result["final_itinerary"])


def test_budget_realism():
    itinerary = _run_case()
    assert itinerary.total_cost >= 400
    assert itinerary.budget_breakdown.get("tickets", 0) >= 0
    assert itinerary.budget_breakdown.get("local_transport", 0) > 0
    assert itinerary.budget_breakdown.get("food_min", 0) > 0


def test_travel_time_nonzero():
    itinerary = _run_case()
    for day in itinerary.days:
        main = [item for item in day.schedule if not item.is_backup]
        for idx, item in enumerate(main):
            if idx == 0:
                continue
            assert item.travel_minutes > 0
            assert item.travel_minutes < 180


def test_ticket_facts_present():
    itinerary = _run_case()
    for day in itinerary.days:
        for item in day.schedule:
            if item.is_backup:
                continue
            assert item.poi.metadata_source == "poi_beijing"
            assert item.poi.open_time
            assert item.poi.ticket_price >= 0


def test_constraints_buffer():
    itinerary = _run_case()
    for day in itinerary.days:
        assert day.meal_windows
        for item in day.schedule:
            if item.is_backup:
                continue
            assert item.buffer_minutes >= 30


def test_no_duplicate_and_route_compactness():
    itinerary = _run_case()
    seen_global: set[str] = set()
    switches = 0

    for day in itinerary.days:
        main = [item for item in day.schedule if not item.is_backup]
        day_ids = [item.poi.id for item in main]
        assert len(day_ids) == len(set(day_ids))

        for poi_id in day_ids:
            assert poi_id not in seen_global
            seen_global.add(poi_id)

        clusters = [item.poi.cluster for item in main if item.poi.cluster]
        for idx in range(1, len(clusters)):
            if clusters[idx] != clusters[idx - 1]:
                switches += 1

    assert switches <= max(2, len(itinerary.days))
