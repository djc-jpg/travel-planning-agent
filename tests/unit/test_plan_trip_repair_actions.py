from app.application.plan_trip import _enrich_result
from app.application.contracts import TripResult, TripStatus


def test_enrich_result_preserves_existing_repair_actions():
    result = TripResult(
        status=TripStatus.DONE,
        message="ok",
        session_id="s1",
        itinerary={
            "city": "杭州",
            "days": [],
            "assumptions": [],
            "repair_actions": ["day1:remove_poi:景点A:budget_trim"],
            "routing_source": "fixture",
        },
    )
    state = {
        "validation_issues": [],
        "repair_attempts": 2,
        "metrics": {"llm_call_count": 0},
    }

    _enrich_result(
        result=result,
        state=state,
        request_id="r1",
        trace_id="t1",
    )

    assert result.itinerary is not None
    actions = result.itinerary.get("repair_actions", [])
    assert "day1:remove_poi:景点A:budget_trim" in actions
    assert "repair_loop_attempts=2" in actions
